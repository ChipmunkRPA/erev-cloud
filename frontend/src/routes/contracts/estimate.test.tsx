// @vitest-environment jsdom
// SF-03:estimates and SF-03:estimate (BUILD_SPEC CTR-25; SCREENS §8; 04 API-R-32, §16.14 estimates,
// T-CON-12, T-CON-13; PRD SM-04, POL-040, POL-042): the master list of estimated elements grouped by
// kind beside the detail of the selected element; the method chip and its lock; the element drawer and
// the version drawer with the preview of the saved draft; the banner of a draft, of a pending request
// and of a reassessment that is due; the versions table with the comparison; the attestation.
import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { RouteObject } from "react-router";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import { modificationKey } from "../../lib/api/queries/modifications";
import {
  installMemoryStorage,
  preloadScreens,
  probeRoute,
  renderApp,
  signedInMe,
} from "../../test/app";
import {
  CONSTRAINT_RECORD_ID,
  constraintRecord,
  EAC_ID,
  EAC_PREVIEW,
  EAC_V2_APPROVAL_ID,
  eacVersions,
  ESTIMATE_APPROVAL_ID,
  estimateRow,
  NEW_ESTIMATE_ID,
  NEW_JUDGEMENT_ID,
  REBATE_ID,
  serveEstimates,
  versionRow,
} from "../../test/estimates";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import {
  AVM_US,
  CONTEXT,
  CONTRACT_ID,
  money,
  PRIYA_USER,
  serveWorkbench,
} from "../../test/workbench";

installMswServer();
installMemoryStorage();
configure({ asyncUtilTimeout: 5000 });

beforeAll(async () => {
  await preloadScreens(SCREEN_ROUTES, ["SF-03:estimates"]);
});

afterEach(() => {
  cleanup();
});

const MAYA = signedInMe({
  permissions: ["contract.read", "contract.create", "estimate.create", "judgement.create"],
});
const READER = signedInMe({ permissions: ["contract.read"] });
const LIST = `/contracts/${CONTRACT_ID}/estimates`;

const ROUTES: readonly RouteObject[] = [
  ...SCREEN_ROUTES.filter((route) => route.id === "SF-03:estimates"),
  probeRoute("SF-03", "/contracts/:contractId/obligations", "contracts.workbench.documentTitle"),
  probeRoute("SF-12:request", "/approvals/requests/:requestId", "approvals.title"),
  probeRoute("SF-02", "/contracts", "contracts.list.title"),
];

function open(path: string, me = MAYA) {
  return renderApp(`${path}${path.includes("?") ? "&" : "?"}${CONTEXT}`, {
    me,
    screenRoutes: ROUTES,
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

function rowOf(table: HTMLElement, header: string): string[] {
  const row = within(table).getByRole("rowheader", { name: header }).closest("tr");
  return cellTexts(row);
}

/** SCREENS §8.9 K-06 `REBATE-DR-01`: most likely amount, version 1 approved. */
function rebate() {
  return estimateRow({
    id: REBATE_ID,
    estimate_kind: "VARIABLE_CONSIDERATION",
    element_code: "REBATE-DR-01",
    vc_element_type: "REBATE",
    direction: "DECREASE",
    method: "MOST_LIKELY_AMOUNT",
  });
}

function rebateVersion(overrides: Parameters<typeof versionRow>[0] = { version_no: 1 }) {
  return versionRow({
    estimate_id: REBATE_ID,
    status: "APPROVED",
    effective_date: "2026-07-01",
    scenarios: [{ outcome: "Threshold not expected", amount: "0.00" }],
    unconstrained_amount: "5750.00",
    most_conservative_amount: "0.00",
    constrained_amount: "0.00",
    excluded_amount: money("5750.00"),
    constraint_checklist: {
      susceptible_to_outside_factors: true,
      long_resolution_period: false,
      limited_experience: false,
      price_concession_practice: false,
      broad_range_of_amounts: false,
    },
    rationale: "Forecast 900 units in the framework year.",
    ...overrides,
  });
}

/** Picks an option of a Select inside `scope`. */
function select(scope: HTMLElement, name: string, option: string): void {
  const trigger = within(scope).getByRole("combobox", { name });
  fireEvent.click(trigger);
  const list = document.getElementById(trigger.getAttribute("aria-controls") ?? "");
  if (list === null) {
    throw new Error(`The select ${name} has no open list`);
  }
  fireEvent.mouseDown(within(list).getByRole("option", { name: option }));
}

function type(element: HTMLElement, value: string) {
  fireEvent.change(element, { target: { value } });
  fireEvent.blur(element);
}

/** An attachment of an estimate version, as `GET /attachments` answers it. */
function evidenceFile(versionId: string, name: string) {
  return {
    id: "a2a2a2a2-a2a2-4a2a-8a2a-a2a2a2a2a2a2",
    subject_type: "estimate_version" as const,
    subject_id: versionId,
    file_object_id: "f2f2f2f2-f2f2-4f2f-8f2f-f2f2f2f2f2f2",
    original_filename: name,
    description: null,
    media_type: "application/pdf",
    size_bytes: 20480,
    sha256: "d".repeat(64),
    created_at: "2026-09-10T09:10:00Z",
    created_by: "u1",
    created_by_kind: "USER" as const,
    voided_at: null,
    voided_by: null,
    voided_by_kind: null,
    void_reason: null,
  };
}

/** The text of an element as a sighted reader sees it: without the visually hidden sign words. */
function shownText(element: HTMLElement): string {
  const shown = element.cloneNode(true) as HTMLElement;
  for (const hidden of shown.querySelectorAll(".sr-only")) {
    hidden.remove();
  }
  return (shown.textContent ?? "").replace(/\s+/g, " ").trim();
}

/** Holds every GET of `path` until `release` is called; the world's handler answers it then. */
function hold(path: string): { readonly release: () => void } {
  let open: () => void = () => undefined;
  const gate = new Promise<void>((resolve) => {
    open = resolve;
  });
  server.use(
    http.get(apiUrl(path), async () => {
      await gate;
    }),
  );
  return { release: () => open() };
}

describe("SF-03:estimate", () => {
  it("method chip locked", async () => {
    serveWorkbench();
    serveEstimates([rebate()], { [REBATE_ID]: [rebateVersion()] });
    open(`${LIST}/${REBATE_ID}`);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    // SCREENS §8.10: the lock is in the chip's accessible name; its text stays the method.
    const chip = await within(pane).findByTestId("SF-03-chip-method");
    expect(chip.getAttribute("aria-label")).toBe("Method most likely amount, locked");
    expect(chip.textContent).toBe("Most likely amount");
    expect(document.getElementById(chip.getAttribute("aria-describedby") ?? "")?.textContent).toBe(
      "The estimation method is fixed after the first version (POL-040).",
    );

    fireEvent.click(within(pane).getByRole("button", { name: "New estimate version" }));
    const drawer = await screen.findByRole("dialog", { name: /^New estimate version/ });
    expect(
      within(drawer).getByRole("heading", {
        level: 2,
        name: "New estimate version · REBATE-DR-01",
      }),
    ).toBeTruthy();
    // After version 1 is approved the method is shown, locked, and is no control of the form.
    const method = within(drawer).getByRole("img", { name: "Method most likely amount, locked" });
    expect(method.textContent).toBe("Most likely amount");
    expect(within(drawer).queryByRole("combobox", { name: /Method/ })).toBeNull();
    expect(within(drawer).queryByRole("radio", { name: /amount|value|Rate|build-up/ })).toBeNull();
    expect(within(drawer).getByText("Rebate")).toBeTruthy();
  });

  it("an element without an approved version shows its method without the lock", async () => {
    serveWorkbench();
    serveEstimates([estimateRow()], {
      [EAC_ID]: [versionRow({ version_no: 1, expected_total_amount: "700000.00" })],
    });
    open(`${LIST}/${EAC_ID}`);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    const chip = await within(pane).findByTestId("SF-03-chip-method");
    expect(chip.textContent).toBe("Cost build-up");
    expect(within(pane).queryByRole("img", { name: /locked/ })).toBeNull();
  });

  it("preview renders api summary", async () => {
    serveWorkbench();
    const world = serveEstimates([estimateRow()], {
      [EAC_ID]: [
        versionRow({
          version_no: 1,
          status: "APPROVED",
          expected_total_amount: "820000.00",
          costs_incurred_to_date: money("502000.00"),
          progress_ratio: "0.612",
        }),
      ],
    });
    // Figures a binary float cannot hold: they reach the screen as the API's decimal strings.
    world.preview = {
      ...EAC_PREVIEW,
      transaction_price_before: money("9007199254740993.07"),
      transaction_price_after: money("9007199254740995.10"),
      catch_up_total: money("-29169.29"),
    };
    open(`${LIST}/${EAC_ID}`);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    fireEvent.click(await within(pane).findByRole("button", { name: "New estimate version" }));
    const drawer = await screen.findByRole("dialog", { name: /^New estimate version/ });
    const region = within(drawer).getByRole("region", { name: "Preview" });
    expect(region.getAttribute("data-testid")).toBe("SF-03-pane-estimate-preview");
    expect(within(region).getByText("The preview runs when the draft is saved.")).toBeTruthy();

    type(within(drawer).getByLabelText("Effective date"), "30 Sep 2026");
    type(within(drawer).getByLabelText("Estimated total costs (USD)"), "850,000.00");
    type(
      within(drawer).getByLabelText("Rationale"),
      "Steel price escalation (supplier notice 24 Sep 2026)",
    );
    fireEvent.click(within(drawer).getByRole("button", { name: "Save draft" }));

    await waitFor(() => expect(world.sent("POST", "/preview")).toHaveLength(1));
    const table = await within(region).findByRole("table", { name: "Before and after (USD)" });
    expect(rowOf(table, "Transaction price")).toEqual([
      "Transaction price",
      "9,007,199,254,740,993.07",
      "9,007,199,254,740,995.10",
    ]);
    expect(rowOf(table, "Revenue Sep 2026")).toEqual([
      "Revenue Sep 2026",
      "226,463.41",
      "197,294.12",
    ]);
    expect(rowOf(table, "Progress")).toEqual(["Progress", "61.2%", "59.1%"]);
    expect(rowOf(table, "Contract liability")).toEqual(["Contract liability", "0.00", "0.00"]);
    expect(rowOf(table, "Contract asset")).toEqual(["Contract asset", "326,200.00", "297,030.71"]);
    expect(
      within(region)
        .getByTestId("SF-03-estimate-preview-catch-up")
        .textContent?.replace(/\s+/g, " ")
        .includes("(29,169.29)"),
    ).toBe(true);
    // The preview is of the version the save created.
    const created = world.versions.get(EAC_ID)?.[0];
    expect(created?.version_no).toBe(2);
    expect(world.sent("POST", "/preview")[0]?.path).toBe(
      `/api/v1/estimate-versions/${created?.id ?? ""}/preview`,
    );
  });

  it("a preview the API withholds from this reader shows the notice in the place of the table, without Run preview, and the next save runs it", async () => {
    const withheld = "You are not shown this preview";
    const stale = "The fields changed after this preview ran. Save the draft to run it again.";
    serveWorkbench();
    const world = serveEstimates([estimateRow()], {
      [EAC_ID]: [versionRow({ version_no: 1, status: "APPROVED" })],
    });
    // 04 API-S-Job `result` rev 1.314: `summary` null with `summary_withheld` true.
    world.previewWithheld = true;
    open(`${LIST}/${EAC_ID}`);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    fireEvent.click(await within(pane).findByRole("button", { name: "New estimate version" }));
    const drawer = await screen.findByRole("dialog", { name: /^New estimate version/ });
    const region = within(drawer).getByRole("region", { name: "Preview" });
    type(within(drawer).getByLabelText("Effective date"), "30 Sep 2026");
    type(within(drawer).getByLabelText("Estimated total costs (USD)"), "850,000.00");
    type(within(drawer).getByLabelText("Rationale"), "Steel price escalation (supplier notice)");
    fireEvent.click(within(drawer).getByRole("button", { name: "Save draft" }));

    const title = await within(region).findByRole("heading", { name: withheld, level: 4 });
    const notice = title.closest("[data-tone]");
    expect(notice?.getAttribute("data-tone")).toBe("info");
    // Inserted after the save: announced politely.
    expect(notice?.getAttribute("role")).toBe("status");
    expect(notice?.textContent).toBe(
      `${withheld}The preview holds figures of legal entities outside your access. It is shown to people whose access covers every entity of the contract's combination group.`,
    );
    // The notice alone: no table, no figure, and no "Run preview", which would be answered the same.
    expect(region.textContent).toBe(`Preview${notice?.textContent ?? ""}`);
    expect(within(region).queryByRole("button")).toBeNull();
    expect(world.sent("POST", "/preview")).toHaveLength(1);
    // The submission does not wait for the preview.
    const submit = within(drawer).getByRole<HTMLButtonElement>("button", {
      name: "Submit for approval",
    });
    expect(submit.disabled).toBe(false);
    expect(submit.getAttribute("aria-disabled")).not.toBe("true");

    // A changed field says how the preview is run again, and the save runs it: an answer that holds
    // the summary shows its table, with "Run preview" as before.
    type(within(drawer).getByLabelText("Rationale"), "Steel price escalation (notice of 24 Sep)");
    expect(region.textContent).toBe(`Preview${stale}${notice?.textContent ?? ""}`);
    expect(within(region).queryByRole("button")).toBeNull();
    world.previewWithheld = false;
    fireEvent.click(within(drawer).getByRole("button", { name: "Save draft" }));

    await within(region).findByRole("table", { name: "Before and after (USD)" });
    expect(world.sent("POST", "/preview")).toHaveLength(2);
    expect(within(region).queryByRole("heading", { name: withheld })).toBeNull();
    expect(within(region).getByRole("button", { name: "Run preview" })).toBeTruthy();
  });

  it("a result without a summary is no notice unless the API says the summary is withheld: the section reads that the preview has not run", async () => {
    serveWorkbench();
    const world = serveEstimates([estimateRow()], {
      [EAC_ID]: [versionRow({ version_no: 1, status: "APPROVED" })],
    });
    // A succeeded job whose result holds neither a summary nor the member: no dry run of the API
    // ends so, and the section says what it said of it before. The job is read once while it runs,
    // so that the sentence that follows the progress is said of its answer.
    let reads = 0;
    server.use(
      http.get(apiUrl("/api/v1/jobs/:jobId"), ({ params }) => {
        reads += 1;
        const ended = reads > 1;
        return HttpResponse.json({
          id: String(params.jobId),
          kind: "CONTRACT_COMPUTE",
          mode: "ESTIMATE_PREVIEW",
          state: ended ? "SUCCEEDED" : "RUNNING",
          progress: { done: ended ? 1 : 0, total: 1 },
          problem: null,
          result: ended
            ? { href: "/api/v1/estimate-versions/x", counts: { events: 1 }, summary: null }
            : null,
          created_by: PRIYA_USER,
          created_at: "2026-09-30T09:40:00Z",
          started_at: "2026-09-30T09:40:01Z",
          finished_at: ended ? "2026-09-30T09:40:03Z" : null,
        });
      }),
    );
    open(`${LIST}/${EAC_ID}`);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    fireEvent.click(await within(pane).findByRole("button", { name: "New estimate version" }));
    const drawer = await screen.findByRole("dialog", { name: /^New estimate version/ });
    const region = within(drawer).getByRole("region", { name: "Preview" });
    type(within(drawer).getByLabelText("Effective date"), "30 Sep 2026");
    type(within(drawer).getByLabelText("Estimated total costs (USD)"), "850,000.00");
    type(within(drawer).getByLabelText("Rationale"), "Steel price escalation (supplier notice)");
    fireEvent.click(within(drawer).getByRole("button", { name: "Save draft" }));

    await waitFor(() => expect(world.sent("POST", "/preview")).toHaveLength(1));
    await within(region).findByRole("progressbar");
    // The job is read again two seconds later.
    await waitFor(
      () =>
        expect(region.textContent).toBe(
          "PreviewThe preview of this draft has not run here yet.Run preview",
        ),
      { timeout: 15_000 },
    );
    expect(reads).toBeGreaterThan(1);
    expect(within(region).queryByRole("heading", { level: 4 })).toBeNull();
  });

  it("the master list groups the elements under their kind and shows the latest version of each", async () => {
    serveWorkbench();
    const world = serveEstimates([estimateRow(), rebate()], {
      [EAC_ID]: eacVersions(),
      [REBATE_ID]: [rebateVersion()],
    });
    world.exceptions = [
      {
        id: "9e9e9e9e-9e9e-4e9e-8e9e-9e9e9e9e9e9e",
        code: "VC_REASSESSMENT_MISSING",
        status: "OPEN",
        business_key: "REBATE-DR-01",
        period_id: "1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e5f",
        contract_id: CONTRACT_ID,
      },
    ];
    open(`${LIST}/${REBATE_ID}`);

    const list = await screen.findByRole("listbox", { name: "Estimated elements" });
    expect(list.getAttribute("data-testid")).toBe("SF-03-grid-estimates");
    const options = await within(list).findAllByRole("option");
    // SCREENS §8.4 order of the kinds: variable consideration before estimated total costs.
    expect(options.map((option) => option.getAttribute("data-testid"))).toEqual([
      "SF-03-row-rebate-dr-01",
      "SF-03-row-eac",
    ]);
    const describedBy = (option: HTMLElement) =>
      document.getElementById(option.getAttribute("aria-describedby") ?? "")?.textContent;
    expect(options.map(describedBy)).toEqual(["Variable consideration", "Estimated total costs"]);
    await waitFor(() =>
      expect(options[1]?.textContent?.replace(/\s+/g, " ")).toBe(
        "EAC850,000.00v3 · effective 30 Sep 2026Pending approval",
      ),
    );
    expect(options[0]?.textContent?.replace(/\s+/g, " ")).toBe(
      "REBATE-DR-010.00v1 · effective 01 Jul 2026ApprovedReassessment due",
    );
    expect(screen.getByText("2 estimated elements")).toBeTruthy();
    expect(within(list).getByRole("option", { name: /^REBATE-DR-01/ })).toBe(options[0]);

    // The selected element with a reassessment that is due (IMP-72): the chip and the banner.
    const pane = screen.getByTestId("SF-03-pane-estimate");
    const banner = await within(pane).findByTestId("SF-03-banner-estimate");
    expect(
      within(banner).getByText(
        'No estimate version or approved "No change" attestation is effective at 30 Sep 2026.',
      ),
    ).toBeTruthy();
    expect(within(banner).getByRole("button", { name: "Attest no change" })).toBeTruthy();
    expect(within(banner).getByRole("button", { name: "New estimate version" })).toBeTruthy();

    // The filter keeps the elements whose code or kind matches.
    type(screen.getByRole("searchbox", { name: "Filter estimates" }), "total costs");
    expect(within(list).getAllByRole("option")).toHaveLength(1);
    expect(screen.getByText("2 estimated elements")).toBeTruthy();
  });

  it("the figures strip names the latest version and the pending version shows its banner", async () => {
    serveWorkbench();
    serveEstimates([estimateRow()], { [EAC_ID]: eacVersions() });
    const request = hold(`/api/v1/approvals/${ESTIMATE_APPROVAL_ID}`);
    open(`${LIST}/${EAC_ID}`);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    expect(await within(pane).findByRole("heading", { level: 2, name: "EAC" })).toBeTruthy();
    const strip = within(pane).getByTestId("SF-03-kpi-strip-estimate");
    expect(within(strip).getByRole("heading", { level: 3 }).textContent).toBe(
      "Estimate figures of version 3 (USD)",
    );
    expect(Array.from(strip.querySelectorAll("dt"), (term) => term.textContent)).toEqual([
      "Estimated total costs",
      "Costs incurred to date",
      "Progress",
    ]);
    expect(Array.from(strip.querySelectorAll("dd"), (value) => value.textContent)).toEqual([
      "850,000.00",
      "502,000.00",
      "59.1%",
    ]);

    // The banner says nothing before the request is read (its slot is busy), then all of it at once.
    const banner = within(pane).getByTestId("SF-03-banner-estimate");
    expect(banner.querySelector("[aria-busy='true']")?.textContent).toBe("Loading Version status");
    expect(within(banner).queryByRole("link", { name: "View request" })).toBeNull();
    expect(within(banner).queryByText(/Version 3/)).toBeNull();
    request.release();
    expect(await within(banner).findByText("Version 3 is waiting for approval.")).toBeTruthy();
    expect(banner.querySelector("[aria-busy='true']")).toBeNull();
    expect(within(banner).getByRole("link", { name: "View request" }).getAttribute("href")).toBe(
      `/approvals/requests/${ESTIMATE_APPROVAL_ID}?${CONTEXT}`,
    );
    expect(within(banner).getByRole("button", { name: "Withdraw request" })).toBeTruthy();
    // A version is open: a new one waits for it.
    expect(
      within(pane)
        .getByRole("button", { name: "New estimate version" })
        .getAttribute("aria-disabled"),
    ).toBe("true");

    // "Current version" is the approved version, not the pending one.
    const current = within(pane).getByTestId("SF-03-estimate-version");
    expect(within(current).getByText("820,000.00")).toBeTruthy();
    expect(within(current).getByText("Change order CO-07 adds 120,000.00 of cost")).toBeTruthy();
    expect(within(current).getByText(PRIYA_USER.display_name)).toBeTruthy();
  });

  it("the current version shows the catch-up it was submitted with and its evidence, once both are read", async () => {
    serveWorkbench();
    const world = serveEstimates([estimateRow()], { [EAC_ID]: eacVersions() });
    const approved = world.versions.get(EAC_ID)?.[1];
    world.attachments.set(approved?.id ?? "", [
      evidenceFile(approved?.id ?? "", "change-order-co-07.pdf"),
    ]);
    const request = hold(`/api/v1/approvals/${EAC_V2_APPROVAL_ID}`);
    open(`${LIST}/${EAC_ID}`);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    const current = await within(pane).findByTestId("SF-03-estimate-version");
    expect(within(current).getByText("820,000.00")).toBeTruthy();
    // SCREENS §8.3 "its preview snapshot": the preview is kept with the version's request, so the
    // block waits for that read and for the attachments, and shows both at once.
    expect(current.querySelector("[aria-busy='true']")?.textContent).toBe(
      "Loading Preview and evidence",
    );
    expect(within(current).queryByText("Evidence")).toBeNull();
    request.release();
    const catchUp = await within(current).findByTestId("SF-03-estimate-version-catch-up");
    expect(shownText(catchUp)).toBe("Catch-up (41,804.88)");
    expect(within(current).getByRole("link", { name: "View request" }).getAttribute("href")).toBe(
      `/approvals/requests/${EAC_V2_APPROVAL_ID}?${CONTEXT}`,
    );
    expect(
      within(within(current).getByRole("list", { name: "Attachments of version 2" }))
        .getByRole("link", { name: "change-order-co-07.pdf" })
        .getAttribute("href"),
    ).toBe("/api/v1/files/f2f2f2f2-f2f2-4f2f-8f2f-f2f2f2f2f2f2/content");
    expect(current.querySelector("[aria-busy='true']")).toBeNull();
    cleanup();

    // A reader the API shows no request to: the evidence without the preview.
    serveWorkbench();
    const unread = serveEstimates([estimateRow()], { [EAC_ID]: eacVersions() });
    unread.attachments.set(approved?.id ?? "", [
      evidenceFile(approved?.id ?? "", "change-order-co-07.pdf"),
    ]);
    server.use(
      http.get(apiUrl(`/api/v1/approvals/${EAC_V2_APPROVAL_ID}`), () =>
        problemResponse("not-found", 404, "Not found"),
      ),
    );
    open(`${LIST}/${EAC_ID}`);
    const second = await within(await screen.findByTestId("SF-03-pane-estimate")).findByTestId(
      "SF-03-estimate-version",
    );
    expect(
      await within(second).findByRole("link", { name: "change-order-co-07.pdf" }),
    ).toBeTruthy();
    expect(within(second).queryByTestId("SF-03-estimate-version-catch-up")).toBeNull();
    expect(within(second).queryByRole("link", { name: "View request" })).toBeNull();
    cleanup();

    // A version that came back is no longer the one its last request previewed: no snapshot.
    serveWorkbench();
    const [latest] = eacVersions();
    if (latest === undefined) {
      throw new Error("the world holds no version 3");
    }
    serveEstimates([estimateRow()], { [EAC_ID]: [{ ...latest, status: "WITHDRAWN" }] });
    open(`${LIST}/${EAC_ID}`);
    const third = await screen.findByTestId("SF-03-pane-estimate");
    expect(
      await within(third).findByText("No version is approved yet. The latest version is shown."),
    ).toBeTruthy();
    const returned = within(third).getByTestId("SF-03-estimate-version");
    await waitFor(() => expect(returned.querySelector("[aria-busy='true']")).toBeNull());
    expect(within(returned).getByText("850,000.00")).toBeTruthy();
    expect(within(returned).queryByTestId("SF-03-estimate-version-catch-up")).toBeNull();
  });

  it("the versions table lists every version and compares two of them", async () => {
    serveWorkbench();
    serveEstimates([estimateRow()], { [EAC_ID]: eacVersions() });
    open(`${LIST}/${EAC_ID}?pane=versions`);

    const table = await screen.findByRole("table", { name: "Versions" });
    expect(table.getAttribute("data-testid")).toBe("SF-03-grid-estimate-versions");
    expect(Array.from(table.querySelectorAll("thead th"), (cell) => cell.textContent)).toEqual([
      "Select",
      "Version",
      "Status",
      "Effective date",
      "Figure",
      "Prepared by",
      "Approved by",
      "Approved at",
      "Rationale",
    ]);
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((row) => cellTexts(row).slice(1, 5))).toEqual([
      ["3", "Pending approval", "30 Sep 2026", "850,000.00"],
      ["2", "Approved", "10 Sep 2026", "820,000.00"],
      ["1", "Superseded", "01 Feb 2026", "700,000.00"],
    ]);

    const compare = () => screen.getByRole("button", { name: "Compare versions" });
    expect(compare().getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(within(table).getByRole("checkbox", { name: "Select version 3" }));
    fireEvent.click(within(table).getByRole("checkbox", { name: "Select version 2" }));
    expect(compare().getAttribute("aria-disabled")).toBeNull();
    fireEvent.click(compare());
    const diff = await screen.findByRole("table", { name: "Changes from version 2 to version 3" });
    expect(
      within(diff)
        .getAllByRole("row")
        .slice(1)
        .map((row) => cellTexts(row)),
    ).toEqual([
      ["~", "Effective date", "10 Sep 2026", "30 Sep 2026"],
      ["~", "Estimated total costs", "820,000.00", "850,000.00"],
      [
        "~",
        "Rationale",
        "Change order CO-07 adds 120,000.00 of cost",
        "Steel price escalation (supplier notice 24 Sep 2026)",
      ],
    ]);
  });

  it("adding an element opens the drawer of its first version, which is saved with its evidence and submitted", async () => {
    serveWorkbench();
    const world = serveEstimates();
    open(LIST);

    expect(
      await screen.findByRole("heading", { level: 3, name: "No estimated elements" }),
    ).toBeTruthy();
    expect(
      screen.getByText("Select an estimated element to see its versions and evidence."),
    ).toBeTruthy();
    // The toolbar and the empty state both offer the command.
    const toolbar = screen.getByRole("searchbox", { name: "Filter estimates" }).parentElement;
    expect(screen.getAllByRole("button", { name: "Add estimated element" })).toHaveLength(2);
    fireEvent.click(
      within(toolbar as HTMLElement).getByRole("button", { name: "Add estimated element" }),
    );
    const element = await screen.findByRole("dialog", { name: "Add estimated element" });
    fireEvent.click(within(element).getByRole("button", { name: "Add element" }));
    expect(await within(element).findByText("Enter the element code.")).toBeTruthy();

    select(element, "Kind", "Estimated total costs");
    type(within(element).getByLabelText("Element code"), "EAC");
    // The kind proposes its method; every method stays selectable.
    expect(within(element).getByRole("combobox", { name: "Method" }).textContent).toContain(
      "Cost build-up",
    );
    fireEvent.click(within(element).getByRole("button", { name: "Add element" }));
    await waitFor(() => expect(world.sent("POST", "/estimates")).toHaveLength(1));
    expect(world.sent("POST", "/estimates")[0]?.body).toEqual({
      estimate_kind: "EAC",
      element_code: "EAC",
      method: "COST_BUILDUP",
      allocation_target: "CONTRACT",
      target_obligation_keys: [],
      vc_element_type: null,
      obligation_key: null,
      allocation_criteria_evidence: null,
    });

    // SCREENS §8.4: "Add element", then the version drawer opens for version 1.
    const drawer = await screen.findByRole("dialog", { name: "New estimate version · EAC" });
    type(within(drawer).getByLabelText("Effective date"), "01 Feb 2026");
    type(within(drawer).getByLabelText("Estimated total costs (USD)"), "700,000.00");
    type(within(drawer).getByLabelText("Rationale"), "Bid estimate at contract inception.");

    // An estimate of total costs is submitted with evidence (SM-04).
    fireEvent.click(within(drawer).getByRole("button", { name: "Submit for approval" }));
    expect(await within(drawer).findByText("Attach at least one evidence file.")).toBeTruthy();
    expect(world.sent("POST", "/versions")).toHaveLength(0);

    const file = new File(["estimate"], "eac-review-castellan-2026-02.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    fireEvent.change(within(drawer).getByLabelText("Evidence"), { target: { files: [file] } });
    fireEvent.click(within(drawer).getByRole("button", { name: "Submit for approval" }));

    await waitFor(() => expect(world.sent("POST", "/submit")).toHaveLength(1));
    expect(world.sent("POST", "/versions")[0]?.body).toEqual({
      effective_date: "2026-02-01",
      rationale: "Bid estimate at contract inception.",
      scenarios: [],
      parameters: {},
      constraint_checklist: null,
      unconstrained_amount: null,
      most_conservative_amount: null,
      constrained_amount: null,
      rate: null,
      expected_total_amount: "700000.00",
      expected_quantity: null,
      amortization_months: null,
    });
    const version = world.versions.get(NEW_ESTIMATE_ID)?.[0];
    // The file is stored as evidence, then attached to the version the save created.
    expect(world.sent("POST", "/api/v1/files")).toHaveLength(1);
    expect(world.sent("POST", "/api/v1/files")[0]?.body).toMatchObject({ purpose: "ATTACHMENT" });
    expect(world.sent("POST", "/api/v1/attachments")[0]?.body).toMatchObject({
      subject_type: "estimate_version",
      subject_id: version?.id,
    });
    expect(world.sent("POST", "/submit")[0]?.body).toEqual({ comment: null });

    // The drawer closes; the pane shows the pending version.
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: /^New estimate version/ })).toBeNull(),
    );
    const pane = screen.getByTestId("SF-03-pane-estimate");
    expect(await within(pane).findByText("Version 1 is waiting for approval.")).toBeTruthy();
    expect(
      await screen.findByText(
        "Submitted for approval. Request APR-000437 is waiting for approval.",
      ),
    ).toBeTruthy();
  });

  it("a draft is edited from its banner, and the API's refusal is shown on the field it names", async () => {
    serveWorkbench();
    const world = serveEstimates([estimateRow()], {
      [EAC_ID]: [
        versionRow({
          version_no: 1,
          expected_total_amount: "700000.00",
          costs_incurred_to_date: money("0.00"),
          progress_ratio: "0",
        }),
      ],
    });
    world.refuse.update = () =>
      problemResponse("eac-below-costs-incurred", 422, "Check the highlighted fields", {
        errors: [
          {
            field: "expected_total_amount",
            sheet: null,
            row: null,
            rule_id: "ERR-13",
            message:
              "Estimated total costs (500,000.00) cannot be lower than costs incurred to date (502,000.00).",
          },
        ],
      });
    const evidence = hold("/api/v1/attachments");
    open(`${LIST}/${EAC_ID}`);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    const banner = await within(pane).findByTestId("SF-03-banner-estimate");
    // The banner shows once the evidence of the draft is read, and it is whole then: no evidence
    // is attached yet, so its submission waits for it.
    expect(banner.querySelector("[aria-busy='true']")?.textContent).toBe("Loading Version status");
    expect(within(banner).queryByText(/Version 1/)).toBeNull();
    evidence.release();
    expect(await within(banner).findByText("Version 1 is a draft.")).toBeTruthy();
    expect(banner.querySelector("[aria-busy='true']")).toBeNull();
    expect(
      within(banner)
        .getByRole("button", { name: "Submit for approval" })
        .getAttribute("aria-disabled"),
    ).toBe("true");
    expect(within(banner).getByText("Attach the evidence to the draft first.")).toBeTruthy();
    // SCREENS §8.3 (rev 1.33): a draft is discarded from its banner too.
    expect(within(banner).getByRole("button", { name: "Discard draft" })).toBeTruthy();

    fireEvent.click(within(banner).getByRole("button", { name: "Edit draft" }));
    const drawer = await screen.findByRole("dialog", { name: "Edit version 1 · EAC" });
    const total = within(drawer).getByLabelText<HTMLInputElement>("Estimated total costs (USD)");
    expect(total.value).toBe("700,000.00");
    expect(within(drawer).getByLabelText<HTMLInputElement>("Effective date").value).toBe(
      "01 Feb 2026",
    );
    type(total, "500,000.00");
    fireEvent.click(within(drawer).getByRole("button", { name: "Save draft" }));

    await waitFor(() =>
      expect(world.sent("PATCH", world.versions.get(EAC_ID)?.[0]?.id ?? "")).toHaveLength(1),
    );
    expect(
      await within(drawer).findByText(
        "Estimated total costs (500,000.00) cannot be lower than costs incurred to date (502,000.00).",
      ),
    ).toBeTruthy();
    expect(total.getAttribute("aria-invalid")).toBe("true");
    expect(world.sent("POST", "/preview")).toHaveLength(0);
  });

  it("an error correction is not submitted as an estimate version", async () => {
    serveWorkbench();
    serveEstimates([estimateRow()], { [EAC_ID]: [] });
    open(`${LIST}/${EAC_ID}`);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    fireEvent.click(await within(pane).findByRole("button", { name: "New estimate version" }));
    const drawer = await screen.findByRole("dialog", { name: /^New estimate version/ });
    const submit = () => within(drawer).getByRole("button", { name: "Submit for approval" });
    expect(submit().getAttribute("aria-disabled")).toBeNull();
    fireEvent.click(within(drawer).getByRole("radio", { name: "Error correction" }));
    expect(
      within(drawer).getByText("Error corrections go through a period reopen with dual approval."),
    ).toBeTruthy();
    expect(submit().getAttribute("aria-disabled")).toBe("true");
    expect(
      within(drawer).getByText("An error correction is not submitted as an estimate version."),
    ).toBeTruthy();
    fireEvent.click(within(drawer).getByRole("radio", { name: "Change in estimate" }));
    expect(submit().getAttribute("aria-disabled")).toBeNull();
  });

  it("a variable consideration version carries its scenarios, the constraint factors and the judgement", async () => {
    serveWorkbench();
    const world = serveEstimates([rebate()], { [REBATE_ID]: [rebateVersion()] });
    open(`${LIST}/${REBATE_ID}`);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    fireEvent.click(await within(pane).findByRole("button", { name: "New estimate version" }));
    const drawer = await screen.findByRole("dialog", { name: /^New estimate version/ });
    // The new version starts from the approved one: its outcome and its figures, not its date.
    expect(within(drawer).getByLabelText<HTMLInputElement>("Effective date").value).toBe("");
    const grid = within(drawer).getByTestId("SF-03-grid-estimate-scenarios");
    expect(
      within(grid)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toContain("Amount (USD)");
    // Most likely amount: outcomes carry no probability.
    expect(within(grid).queryByRole("columnheader", { name: /Probability/ })).toBeNull();
    expect(within(drawer).getByLabelText<HTMLInputElement>("Constrained amount (USD)").value).toBe(
      "0.00",
    );
    expect(within(drawer).getByText("Between 0.00 and 5,750.00.")).toBeTruthy();

    type(within(drawer).getByLabelText("Effective date"), "30 Sep 2026");
    type(within(drawer).getByLabelText("Constrained amount (USD)"), "5,750.00");
    fireEvent.click(
      within(drawer).getByRole("checkbox", { name: "Broad range of possible amounts" }),
    );
    type(
      within(drawer).getByLabelText("Rationale"),
      "Customer acquired Tessen Werke; forecast 1,450 units in the framework year.",
    );
    type(
      within(drawer).getByLabelText(/^Constraint conclusion/),
      "A significant reversal is not probable: the threshold is expected to be met.",
    );
    fireEvent.click(within(drawer).getByRole("button", { name: "Save draft" }));

    await waitFor(() => expect(world.sent("POST", "/preview")).toHaveLength(1));
    expect(world.sent("POST", "/versions")[0]?.body).toEqual({
      effective_date: "2026-09-30",
      rationale: "Customer acquired Tessen Werke; forecast 1,450 units in the framework year.",
      scenarios: [{ outcome: "Threshold not expected", amount: "0.00" }],
      parameters: {},
      constraint_checklist: {
        susceptible_to_outside_factors: true,
        long_resolution_period: false,
        limited_experience: false,
        price_concession_practice: false,
        broad_range_of_amounts: true,
      },
      unconstrained_amount: "5750.00",
      most_conservative_amount: "0.00",
      constrained_amount: "5750.00",
      rate: null,
      expected_total_amount: null,
      expected_quantity: null,
      amortization_months: null,
    });
    const version = world.versions.get(REBATE_ID)?.[0];
    expect(world.sent("POST", "/api/v1/judgements")[0]?.body).toEqual({
      topic: "CONSTRAINT",
      subject_type: "estimate_version",
      subject_id: version?.id,
      // The route defaults no contract for an estimate version: the screen names it.
      contract_id: CONTRACT_ID,
      conclusion: "A significant reversal is not probable: the threshold is expected to be met.",
      rationale: "Customer acquired Tessen Werke; forecast 1,450 units in the framework year.",
      questionnaire: { estimate_key: "REBATE-DR-01", remote: false },
    });
    expect(world.sent("POST", "/submit")).toHaveLength(1);
    expect(world.sent("PATCH", version?.id ?? "")[0]?.body).toEqual({
      judgement_record_id: "7a7a7a7a-7a7a-4a7a-8a7a-7a7a7a7a7a7a",
    });
    // The record is linked: the drawer names it and offers no second one.
    expect(await within(drawer).findByText(/^JDG-000052 · /)).toBeTruthy();
    expect(within(drawer).queryByLabelText(/^Constraint conclusion/)).toBeNull();
  });

  it("a constraint record whose create gets no answer goes out again under the key it had", async () => {
    // DG-FE-05 rev 1.156 (item W-23): the steps of a press take their keys from the drawer. The API
    // replays the record it created when its answer was lost; a key made per call created a second.
    serveWorkbench();
    const world = serveEstimates([rebate()], { [REBATE_ID]: [rebateVersion()] });
    const keys: (string | null)[] = [];
    server.use(
      http.post(apiUrl("/api/v1/judgements"), ({ request }) => {
        keys.push(request.headers.get("Idempotency-Key"));
        // The first create gets no answer; the next one reaches the world's own handler.
        return keys.length === 1 ? HttpResponse.error() : undefined;
      }),
    );
    open(`${LIST}/${REBATE_ID}`);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    fireEvent.click(await within(pane).findByRole("button", { name: "New estimate version" }));
    const drawer = await screen.findByRole("dialog", { name: /^New estimate version/ });
    type(within(drawer).getByLabelText("Effective date"), "30 Sep 2026");
    type(within(drawer).getByLabelText("Rationale"), "Forecast 1,450 units in the framework year.");
    type(
      within(drawer).getByLabelText(/^Constraint conclusion/),
      "A significant reversal is not probable.",
    );
    const save = () => within(drawer).getByRole("button", { name: "Save draft" });

    fireEvent.click(save());
    await waitFor(() => expect(keys).toHaveLength(1));
    expect(keys[0]).toMatch(/^[0-9a-f-]{36}$/);
    // No answer: the drawer says so and keeps its input; nothing reached the API's own handler.
    expect(
      await within(drawer).findByText("The server could not be reached. Try again."),
    ).toBeTruthy();
    expect(world.sent("POST", "/api/v1/judgements")).toHaveLength(0);
    expect(within(drawer).getByLabelText<HTMLTextAreaElement>(/^Constraint conclusion/).value).toBe(
      "A significant reversal is not probable.",
    );

    await waitFor(() => expect(save().getAttribute("aria-busy")).toBeNull());
    fireEvent.click(save());
    await waitFor(() => expect(world.sent("POST", "/submit")).toHaveLength(1));
    expect(keys).toHaveLength(2);
    expect(keys[1]).toBe(keys[0]);
    expect(world.sent("POST", "/api/v1/judgements")).toHaveLength(1);
    // The version the first press created is the one the second press changed: no second version.
    expect(world.sent("POST", "/versions")).toHaveLength(1);
    expect(world.versions.get(REBATE_ID)).toHaveLength(2);
  });

  it("the preparer withdraws the pending request, and another reader is not offered the command", async () => {
    serveWorkbench();
    const world = serveEstimates([estimateRow()], { [EAC_ID]: eacVersions() });
    open(`${LIST}/${EAC_ID}`);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    fireEvent.click(await within(pane).findByRole("button", { name: "Withdraw request" }));
    const dialog = await screen.findByRole("dialog", { name: "Withdraw this request?" });
    expect(
      within(dialog).getByText("The approval request is closed and version 3 can be edited again."),
    ).toBeTruthy();
    type(within(dialog).getByLabelText(/^Comment/), "The supplier notice was revised.");
    fireEvent.click(within(dialog).getByRole("button", { name: "Withdraw request" }));
    await waitFor(() => expect(world.sent("POST", "/withdraw")).toHaveLength(1));
    expect(world.sent("POST", "/withdraw")[0]?.body).toEqual({
      comment: "The supplier notice was revised.",
    });
    const returned = within(pane).getByTestId("SF-03-banner-estimate");
    expect(
      await within(returned).findByText("Version 3 was withdrawn. Edit it to submit it again."),
    ).toBeTruthy();
    expect(returned.querySelector("[data-tone]")?.getAttribute("data-tone")).toBe("info");
    expect(within(returned).getByRole("link", { name: "View request" }).getAttribute("href")).toBe(
      `/approvals/requests/${ESTIMATE_APPROVAL_ID}?${CONTEXT}`,
    );
    expect(within(returned).getByRole("button", { name: "Edit draft" })).toBeTruthy();
    cleanup();

    serveWorkbench();
    const other = serveEstimates([estimateRow()], { [EAC_ID]: eacVersions() });
    other.requestPreparer = PRIYA_USER;
    open(`${LIST}/${EAC_ID}`);
    const second = await screen.findByTestId("SF-03-pane-estimate");
    const banner = await within(second).findByTestId("SF-03-banner-estimate");
    expect(await within(banner).findByText("Version 3 is waiting for approval.")).toBeTruthy();
    // The banner is whole when it shows: the request is another preparer's, so no withdrawal.
    expect(within(banner).getByRole("link", { name: "View request" })).toBeTruthy();
    expect(within(banner).queryByRole("button", { name: "Withdraw request" })).toBeNull();
    cleanup();

    // A reader the API shows no request to: the pending banner without the withdrawal.
    serveWorkbench();
    serveEstimates([estimateRow()], { [EAC_ID]: eacVersions() });
    server.use(
      http.get(apiUrl(`/api/v1/approvals/${ESTIMATE_APPROVAL_ID}`), () =>
        problemResponse("not-found", 404, "Not found"),
      ),
    );
    open(`${LIST}/${EAC_ID}`);
    const third = await screen.findByTestId("SF-03-pane-estimate");
    const unread = await within(third).findByTestId("SF-03-banner-estimate");
    expect(await within(unread).findByText("Version 3 is waiting for approval.")).toBeTruthy();
    expect(within(unread).getByRole("link", { name: "View request" })).toBeTruthy();
    expect(within(unread).queryByRole("button", { name: "Withdraw request" })).toBeNull();
  });

  it("a version whose request the API voided says so in the words of the approvals screens", async () => {
    serveWorkbench();
    const [latest, ...earlier] = eacVersions();
    if (latest === undefined) {
      throw new Error("the world holds no version 3");
    }
    // 04 E-12: `on_voided` returns the version to WITHDRAWN whoever voided its request.
    const world = serveEstimates([estimateRow()], {
      [EAC_ID]: [{ ...latest, status: "WITHDRAWN" }, ...earlier],
    });
    world.voidReason = "STALE_SUBJECT";
    const request = hold(`/api/v1/approvals/${ESTIMATE_APPROVAL_ID}`);
    open(`${LIST}/${EAC_ID}`);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    const banner = await within(pane).findByTestId("SF-03-banner-estimate");
    // The request decides the sentence: nothing is said before it is read.
    expect(banner.querySelector("[aria-busy='true']")).not.toBeNull();
    expect(within(banner).queryByText(/[Vv]ersion 3/)).toBeNull();
    request.release();
    expect(
      await within(banner).findByText(
        "The approval request of version 3 was voided: this item changed after submission. Edit the version to submit it again.",
      ),
    ).toBeTruthy();
    expect(within(banner).queryByText(/was withdrawn/)).toBeNull();
    expect(banner.querySelector("[data-tone]")?.getAttribute("data-tone")).toBe("warning");
    expect(within(banner).getByRole("link", { name: "View request" }).getAttribute("href")).toBe(
      `/approvals/requests/${ESTIMATE_APPROVAL_ID}?${CONTEXT}`,
    );
    // The version is the preparer's again: it is edited, and a new one may start beside it.
    expect(within(banner).getByRole("button", { name: "Edit draft" })).toBeTruthy();
    expect(within(banner).queryByRole("button", { name: "Withdraw request" })).toBeNull();
    expect(
      within(pane)
        .getByRole("button", { name: "New estimate version" })
        .getAttribute("aria-disabled"),
    ).toBeNull();
  });

  it("a rejected version names its request without reading it, and an unknown void reads as withdrawn", async () => {
    serveWorkbench();
    const [latest, ...earlier] = eacVersions();
    if (latest === undefined) {
      throw new Error("the world holds no version 3");
    }
    let reads = 0;
    serveEstimates([estimateRow()], { [EAC_ID]: [{ ...latest, status: "REJECTED" }, ...earlier] });
    server.use(
      http.get(apiUrl(`/api/v1/approvals/${ESTIMATE_APPROVAL_ID}`), () => {
        reads += 1;
        return problemResponse("not-found", 404, "Not found");
      }),
    );
    open(`${LIST}/${EAC_ID}`);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    const banner = await within(pane).findByTestId("SF-03-banner-estimate");
    expect(
      within(banner).getByText("Version 3 was rejected. Edit it to submit it again."),
    ).toBeTruthy();
    expect(within(banner).getByRole("link", { name: "View request" }).getAttribute("href")).toBe(
      `/approvals/requests/${ESTIMATE_APPROVAL_ID}?${CONTEXT}`,
    );
    expect(within(banner).getByRole("button", { name: "Edit draft" })).toBeTruthy();
    expect(reads).toBe(0);
    cleanup();

    // A withdrawn version whose request cannot be read keeps the plain sentence.
    serveWorkbench();
    serveEstimates([estimateRow()], { [EAC_ID]: [{ ...latest, status: "WITHDRAWN" }, ...earlier] });
    server.use(
      http.get(apiUrl(`/api/v1/approvals/${ESTIMATE_APPROVAL_ID}`), () =>
        problemResponse("not-found", 404, "Not found"),
      ),
    );
    open(`${LIST}/${EAC_ID}`);
    const second = await screen.findByTestId("SF-03-pane-estimate");
    const plain = await within(second).findByTestId("SF-03-banner-estimate");
    expect(
      await within(plain).findByText("Version 3 was withdrawn. Edit it to submit it again."),
    ).toBeTruthy();
    expect(plain.querySelector("[data-tone]")?.getAttribute("data-tone")).toBe("info");
  });

  it("a discarded version (E-12 VOIDED, ruling R-119 (e)) is listed as void and holds no new version back", async () => {
    serveWorkbench();
    serveEstimates([rebate()], {
      [REBATE_ID]: [
        rebateVersion({
          version_no: 2,
          status: "VOIDED",
          effective_date: "2026-09-30",
          unconstrained_amount: "9000.00",
          constrained_amount: "4000.00",
        }),
        rebateVersion(),
      ],
    });
    open(`${LIST}/${REBATE_ID}?pane=versions`);

    const table = await screen.findByRole("table", { name: "Versions" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((row) => cellTexts(row).slice(1, 3))).toEqual([
      ["2", "Void"],
      ["1", "Approved"],
    ]);
    const pane = screen.getByTestId("SF-03-pane-estimate");
    expect(within(pane).queryByTestId("SF-03-banner-estimate")).toBeNull();
    // "Latest" is the highest version number that is not VOIDED (04 §16.14 rev 1.210): the master
    // row and the strip show version 1 with its own figure, not the discarded version 2.
    const list = screen.getByRole("listbox", { name: "Estimated elements" });
    await waitFor(() =>
      expect(within(list).getByRole("option").textContent?.replace(/\s+/g, " ")).toBe(
        "REBATE-DR-010.00v1 · effective 01 Jul 2026Approved",
      ),
    );
    expect(
      within(within(pane).getByTestId("SF-03-kpi-strip-estimate")).getByRole("heading", {
        level: 3,
      }).textContent,
    ).toBe("Estimate figures of version 1 (USD)");
    fireEvent.keyDown(within(pane).getByRole("heading", { level: 2, name: "REBATE-DR-01" }), {
      key: "n",
    });
    expect(await screen.findByRole("dialog", { name: /^New estimate version/ })).toBeTruthy();
  });

  it("Discard draft voids the draft after a confirmation, and the version before it is the latest again", async () => {
    serveWorkbench();
    const world = serveEstimates([rebate()], {
      [REBATE_ID]: [
        rebateVersion({
          version_no: 2,
          status: "DRAFT",
          effective_date: "2026-09-30",
          unconstrained_amount: "9000.00",
          constrained_amount: "4000.00",
        }),
        rebateVersion(),
      ],
    });
    const draftId = world.versions.get(REBATE_ID)?.[0]?.id ?? "";
    open(`${LIST}/${REBATE_ID}?pane=versions`);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    const banner = await within(pane).findByTestId("SF-03-banner-estimate");
    expect(await within(banner).findByText("Version 2 is a draft.")).toBeTruthy();
    // The draft holds a new version and an attestation back; the reason names the two commands
    // that end a draft, and "Discard draft" is one of them.
    const reason = (name: string) => {
      const command = within(pane).getByRole("button", { name });
      expect(command.getAttribute("aria-disabled")).toBe("true");
      return document.getElementById(command.getAttribute("aria-describedby") ?? "")?.textContent;
    };
    expect(reason("New estimate version")).toBe(
      "Version 2 is a draft. Submit or discard it first.",
    );
    expect(reason("Attest no change")).toBe("Version 2 is a draft. Submit or discard it first.");
    fireEvent.click(within(banner).getByRole("button", { name: "Discard draft" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Discard this draft version?" });
    expect(
      within(dialog).getByText(
        "The version is voided. It keeps its number and can no longer be edited or submitted.",
      ),
    ).toBeTruthy();
    expect(world.sent("POST", "/discard")).toHaveLength(0);
    fireEvent.click(within(dialog).getByRole("button", { name: "Discard draft" }));

    // 04 §16.14 rev 1.210: the command takes no body.
    await waitFor(() => expect(world.sent("POST", "/discard")).toHaveLength(1));
    expect(world.sent("POST", "/discard")[0]).toEqual({
      method: "POST",
      path: `/api/v1/estimate-versions/${draftId}/discard`,
      body: null,
    });
    expect(await screen.findByText("Version 2 was discarded.")).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    // The version keeps its number and reads Void; version 1 is the latest one again.
    await waitFor(() =>
      expect(
        within(screen.getByRole("table", { name: "Versions" }))
          .getAllByRole("row")
          .slice(1)
          .map((row) => cellTexts(row).slice(1, 3)),
      ).toEqual([
        ["2", "Void"],
        ["1", "Approved"],
      ]),
    );
    await waitFor(() => expect(within(pane).queryByTestId("SF-03-banner-estimate")).toBeNull());
    expect(
      within(within(pane).getByTestId("SF-03-kpi-strip-estimate")).getByRole("heading", {
        level: 3,
      }).textContent,
    ).toBe("Estimate figures of version 1 (USD)");
    const list = screen.getByRole("listbox", { name: "Estimated elements" });
    await waitFor(() =>
      expect(within(list).getByRole("option").textContent?.replace(/\s+/g, " ")).toBe(
        "REBATE-DR-010.00v1 · effective 01 Jul 2026Approved",
      ),
    );
    expect(
      within(pane)
        .getByRole("button", { name: "New estimate version" })
        .getAttribute("aria-disabled"),
    ).toBeNull();
  });

  it("a refused discard shows the API's messages, and the draft stays", async () => {
    serveWorkbench();
    const world = serveEstimates([rebate()], {
      [REBATE_ID]: [
        rebateVersion({ version_no: 2, status: "DRAFT", effective_date: "2026-09-30" }),
        rebateVersion(),
      ],
    });
    // 04 §16.14 rev 1.210: a version that is no draft any more (another session submitted it).
    world.refuse.discard = () =>
      problemResponse("invalid-transition", 409, "Action not available in this state", {
        errors: [
          {
            field: null,
            rule_id: "DB-03",
            message: "Only a draft estimate version can be discarded.",
          },
        ],
      });
    open(`${LIST}/${REBATE_ID}`);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    const banner = await within(pane).findByTestId("SF-03-banner-estimate");
    fireEvent.click(await within(banner).findByRole("button", { name: "Discard draft" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Discard this draft version?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Discard draft" }));

    expect(
      await within(dialog).findByText("Only a draft estimate version can be discarded."),
    ).toBeTruthy();
    expect(within(dialog).getByText("Action not available in this state")).toBeTruthy();
    expect(world.versions.get(REBATE_ID)?.[0]?.status).toBe("DRAFT");
    expect(screen.queryByText("Version 2 was discarded.")).toBeNull();
  });

  it("a draft of a discarded modification is not submitted: the banner shows the API's sentence and keeps Discard draft", async () => {
    serveWorkbench();
    const world = serveEstimates([rebate()], {
      [REBATE_ID]: [
        rebateVersion({
          version_no: 2,
          status: "DRAFT",
          effective_date: "2026-09-30",
          modification_id: "5d5d5d5d-5d5d-45d5-85d5-5d5d5d5d5d5d",
          judgement_record_id: CONSTRAINT_RECORD_ID,
        }),
        rebateVersion(),
      ],
    });
    // The draft holds the evidence its kind needs and names its constraint record, sent for review
    // (04 §16.14 rev 1.241), so the banner offers the submission.
    const draftId = world.versions.get(REBATE_ID)?.[0]?.id ?? "";
    world.attachments.set(draftId, [evidenceFile(draftId, "rebate-forecast-2026-09.pdf")]);
    world.judgements.set(draftId, [constraintRecord(draftId)]);
    // 04 §16.14 rev 1.210, PRD ERR-88: the modification the version was created inside is VOIDED.
    const sentence =
      "Modification MOD-000003 of this estimate version was discarded. The version cannot be submitted.";
    world.refuse.submit = () =>
      problemResponse("invalid-transition", 409, "Action not available in this state", {
        errors: [{ field: null, rule_id: "SM-04", message: sentence }],
      });
    open(`${LIST}/${REBATE_ID}`);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    const banner = await within(pane).findByTestId("SF-03-banner-estimate");
    const submit = await within(banner).findByRole("button", { name: "Submit for approval" });
    expect(submit.getAttribute("aria-disabled")).toBeNull();
    fireEvent.click(submit);

    await waitFor(() => expect(world.sent("POST", "/submit")).toHaveLength(1));
    expect(await within(banner).findByText(sentence)).toBeTruthy();
    expect(world.versions.get(REBATE_ID)?.[0]?.status).toBe("DRAFT");
    // The version stays a draft with its commands: the discard is the way out of it.
    expect(within(banner).getByText("Version 2 is a draft.")).toBeTruthy();
    expect(within(banner).getByRole("button", { name: "Discard draft" })).toBeTruthy();
    expect(screen.queryByText(/^Submitted for approval/)).toBeNull();
  });

  it("an estimate command marks the modification rows for a new read: a row lists the versions created inside it", async () => {
    serveWorkbench();
    const modificationId = "5d5d5d5d-5d5d-45d5-85d5-5d5d5d5d5d5d";
    const world = serveEstimates([rebate()], {
      [REBATE_ID]: [
        rebateVersion({
          version_no: 2,
          status: "DRAFT",
          effective_date: "2026-09-30",
          modification_id: modificationId,
          judgement_record_id: CONSTRAINT_RECORD_ID,
        }),
        rebateVersion(),
      ],
    });
    const draftId = world.versions.get(REBATE_ID)?.[0]?.id ?? "";
    world.attachments.set(draftId, [evidenceFile(draftId, "rebate-forecast-2026-09.pdf")]);
    world.judgements.set(draftId, [constraintRecord(draftId)]);
    const { queryClient } = open(`${LIST}/${REBATE_ID}`);
    // The row as the wizard read it before the member came here: it lists the version as a draft.
    const rowKey = modificationKey(modificationId);
    queryClient.setQueryData(rowKey, { id: modificationId });
    expect(queryClient.getQueryState(rowKey)?.isInvalidated).toBe(false);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    const banner = await within(pane).findByTestId("SF-03-banner-estimate");
    fireEvent.click(await within(banner).findByRole("button", { name: "Submit for approval" }));

    // 04 §16.14 rev 1.210 `linked_estimate_versions`: the version waits for approval now, and SF-07
    // reads its row again when it is opened.
    expect(await within(banner).findByText("Version 2 is waiting for approval.")).toBeTruthy();
    await waitFor(() => expect(queryClient.getQueryState(rowKey)?.isInvalidated).toBe(true));
  });

  it("an attestation repeats the approved figures with the no-change parameter and is submitted", async () => {
    serveWorkbench();
    const world = serveEstimates([rebate()], { [REBATE_ID]: [rebateVersion()] });
    open(`${LIST}/${REBATE_ID}`);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    fireEvent.click(await within(pane).findByRole("button", { name: "Attest no change" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Attest no change for REBATE-DR-01?",
    });
    // The effective date starts at the end of the context period.
    expect(within(dialog).getByLabelText<HTMLInputElement>("Effective date").value).toBe(
      "30 Sep 2026",
    );
    expect(
      within(dialog).getByText(
        "The approved version 1 still applies at 30 Sep 2026. The attestation goes to approval.",
      ),
    ).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "Submit attestation" }));
    expect(await within(dialog).findByText("Enter at least 10 characters.")).toBeTruthy();
    expect(world.sent("POST", "/versions")).toHaveLength(0);

    type(within(dialog).getByLabelText("Rationale"), "Forecast unchanged at 900 units.");
    fireEvent.click(within(dialog).getByRole("button", { name: "Submit attestation" }));
    await waitFor(() => expect(world.sent("POST", "/submit")).toHaveLength(1));
    expect(world.sent("POST", "/versions")[0]?.body).toEqual({
      effective_date: "2026-09-30",
      rationale: "Forecast unchanged at 900 units.",
      scenarios: [{ outcome: "Threshold not expected", amount: "0.00" }],
      parameters: { no_change_attestation: true },
      constraint_checklist: {
        susceptible_to_outside_factors: true,
        long_resolution_period: false,
        limited_experience: false,
        price_concession_practice: false,
        broad_range_of_amounts: false,
      },
      unconstrained_amount: "5750.00",
      most_conservative_amount: "0.00",
      constrained_amount: "0.00",
      rate: null,
      expected_total_amount: null,
      expected_quantity: null,
      amortization_months: null,
    });
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: /^Attest no change/ })).toBeNull(),
    );
    expect(await within(pane).findByText(/^Version 2 is waiting for approval\.$/)).toBeTruthy();
  });

  it("the evidence pane lists the attachments and the judgement records of every version", async () => {
    serveWorkbench();
    const world = serveEstimates([rebate()], {
      [REBATE_ID]: [
        rebateVersion({ version_no: 2, status: "DRAFT", effective_date: "2026-09-30" }),
        rebateVersion(),
      ],
    });
    const [draft, approved] = world.versions.get(REBATE_ID) ?? [];
    world.attachments.set(approved?.id ?? "", [
      {
        id: "a1a1a1a1-a1a1-4a1a-8a1a-a1a1a1a1a1a1",
        subject_type: "estimate_version",
        subject_id: approved?.id ?? "",
        file_object_id: "f1f1f1f1-f1f1-4f1f-8f1f-f1f1f1f1f1f1",
        original_filename: "rebate-forecast-drossel-2026-07.pdf",
        description: null,
        media_type: "application/pdf",
        size_bytes: 20480,
        sha256: "d".repeat(64),
        created_at: "2026-07-01T09:10:00Z",
        created_by: "u1",
        created_by_kind: "USER",
        voided_at: null,
        voided_by: null,
        voided_by_kind: null,
        void_reason: null,
      },
    ]);
    world.judgements.set(draft?.id ?? "", [
      {
        id: "7b7b7b7b-7b7b-4b7b-8b7b-7b7b7b7b7b7b",
        judgement_no: "JDG-000061",
        topic: "CONSTRAINT",
        subject_type: "estimate_version",
        subject_id: draft?.id ?? "",
        contract_id: CONTRACT_ID,
        book: null,
        status: "SUBMITTED",
        conclusion: "A significant reversal is not probable.",
        rationale: "The threshold is expected to be met.",
        alternatives_considered: null,
        codification_refs: [],
        questionnaire: { estimate_key: "REBATE-DR-01", remote: false },
        content_sha256: null,
        approval_request_id: null,
        supersedes_id: null,
        reviewer: null,
        reviewed_at: null,
        created_by: PRIYA_USER,
        created_at: "2026-09-30T09:36:00Z",
        updated_at: "2026-09-30T09:36:00Z",
      },
    ]);
    open(`${LIST}/${REBATE_ID}?pane=evidence`);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    const second = await within(pane).findByRole("region", { name: "Version 2" });
    expect(within(second).getByText("JDG-000061")).toBeTruthy();
    expect(within(second).getByText("A significant reversal is not probable.")).toBeTruthy();
    expect(within(second).queryByRole("table")).toBeNull();
    const first = within(pane).getByRole("region", { name: "Version 1" });
    const link = within(first).getByRole("link", { name: "rebate-forecast-drossel-2026-07.pdf" });
    expect(link.getAttribute("href")).toBe(
      "/api/v1/files/f1f1f1f1-f1f1-4f1f-8f1f-f1f1f1f1f1f1/content",
    );
    expect(within(first).getByText("20,480 bytes")).toBeTruthy();
    // The tab is in the URL; "Current version" leaves it without the parameter.
    fireEvent.click(within(pane).getByRole("tab", { name: "Current version" }));
    expect(await within(pane).findByTestId("SF-03-estimate-version")).toBeTruthy();
  });

  it("N opens the drawer from the pane, not from a field and not while a version is open", async () => {
    serveWorkbench();
    serveEstimates([rebate()], { [REBATE_ID]: [rebateVersion()] });
    open(`${LIST}/${REBATE_ID}`);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    const heading = await within(pane).findByRole("heading", { level: 2, name: "REBATE-DR-01" });
    // Outside the pane the key is the page's.
    fireEvent.keyDown(document.body, { key: "n" });
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.keyDown(screen.getByRole("searchbox", { name: "Filter estimates" }), { key: "n" });
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.keyDown(heading, { key: "n" });
    expect(await screen.findByRole("dialog", { name: /^New estimate version/ })).toBeTruthy();
    cleanup();

    // A draft is open: a second version waits for it, also from the keyboard.
    serveWorkbench();
    serveEstimates([estimateRow()], {
      [EAC_ID]: [versionRow({ version_no: 1, expected_total_amount: "700000.00" })],
    });
    open(`${LIST}/${EAC_ID}`);
    const second = await screen.findByTestId("SF-03-pane-estimate");
    const title = await within(second).findByRole("heading", { level: 2, name: "EAC" });
    await within(second).findByText("Version 1 is a draft.");
    fireEvent.keyDown(title, { key: "n" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("the commands ask estimate.create for the contract's entity, not for some entity", async () => {
    // SCREENS §0.6 SCR-PERM-02 (a), rev 1.30: an estimate is a record of the contract's legal entity.
    // A command held for another entity only is not rendered, exactly like a command not held.
    const scoped = (entityId: string) =>
      signedInMe({
        permissions: ["contract.read", "estimate.create", "judgement.create"],
        permission_scopes: {
          "contract.read": "*",
          "estimate.create": [entityId],
          "judgement.create": [entityId],
        },
      });
    serveWorkbench();
    serveEstimates([rebate()], { [REBATE_ID]: [rebateVersion()] });
    open(`${LIST}/${REBATE_ID}`, scoped("0a1b2c3d-4e5f-4a6b-8c7d-0000000000ff"));

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    expect(
      await within(pane).findByRole("heading", { level: 2, name: "REBATE-DR-01" }),
    ).toBeTruthy();
    expect(await within(pane).findByTestId("SF-03-estimate-version")).toBeTruthy();
    expect(within(pane).queryByRole("button", { name: "New estimate version" })).toBeNull();
    expect(within(pane).queryByRole("button", { name: "Attest no change" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add estimated element" })).toBeNull();
    cleanup();

    serveWorkbench();
    serveEstimates([rebate()], { [REBATE_ID]: [rebateVersion()] });
    open(`${LIST}/${REBATE_ID}`, scoped(AVM_US.id));
    const second = await screen.findByTestId("SF-03-pane-estimate");
    fireEvent.click(await within(second).findByRole("button", { name: "New estimate version" }));
    const drawer = await screen.findByRole("dialog", { name: /^New estimate version/ });
    // judgement.create is held for the entity too: the constraint conclusion is offered.
    expect(within(drawer).getByLabelText(/^Constraint conclusion/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Add estimated element" })).toBeTruthy();
  });

  it("a reader without estimate.create sees the element and no command", async () => {
    serveWorkbench();
    serveEstimates([rebate()], { [REBATE_ID]: [rebateVersion()] });
    open(`${LIST}/${REBATE_ID}`, READER);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    expect(
      await within(pane).findByRole("heading", { level: 2, name: "REBATE-DR-01" }),
    ).toBeTruthy();
    expect(within(pane).queryByRole("button", { name: "New estimate version" })).toBeNull();
    expect(within(pane).queryByRole("button", { name: "Attest no change" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add estimated element" })).toBeNull();
    // The overflow menu stays: comparing and copying a link change nothing.
    expect(
      within(pane).getByRole("button", { name: "More actions for REBATE-DR-01" }),
    ).toBeTruthy();
  });
});

// SCREENS §8.3 and §8.4, as bound (rev 1.64; item EST-DRAWER-JUDGEMENT-1; 04 §16.14 rev 1.241; PRD SM-04,
// ERR-93, ERR-94, IMP-138 to IMP-141): a variable-consideration version is submitted with the CONSTRAINT
// judgement record of its element — sent for review or reviewed — and one version of an element is open
// at a time. The record is asked at the submission; a new version records its own conclusion; a record
// that does not stand is replaced; the banners say what the submission and the approval wait for.
describe("SF-03:estimate, the constraint's judgement record and the open version", () => {
  const NO_JUDGEMENT = signedInMe({
    permissions: ["contract.read", "contract.create", "estimate.create"],
  });
  const REQUIRED =
    "Write the constraint conclusion. A variable consideration version names its judgement record.";
  const NEEDS_PERMISSION =
    "Recording the constraint conclusion needs the permission judgement.create.";
  const CONCLUSION_FIRST = "Record the constraint conclusion in the draft first.";
  const EVIDENCE_FIRST = "Attach the evidence to the draft first.";
  const LINKED = { judgement_record_id: CONSTRAINT_RECORD_ID };

  /**
   * `REBATE-DR-01` with version 1 approved and version 2 beside it — a draft unless `members` say
   * otherwise — with its evidence and, where a status is given, its record under that status.
   */
  function withSecond(
    members: Partial<Parameters<typeof versionRow>[0]> = {},
    options: { readonly record?: string; readonly evidence?: boolean } = {},
  ) {
    const world = serveEstimates([rebate()], {
      [REBATE_ID]: [
        rebateVersion({
          version_no: 2,
          status: "DRAFT",
          effective_date: "2026-09-30",
          ...members,
        }),
        rebateVersion(),
      ],
    });
    const id = world.versions.get(REBATE_ID)?.[0]?.id ?? "";
    if (options.evidence !== false) {
      world.attachments.set(id, [evidenceFile(id, "rebate-forecast-2026-09.pdf")]);
    }
    if (options.record !== undefined) {
      world.judgements.set(id, [constraintRecord(id, { status: options.record })]);
    }
    return { world, id };
  }

  /** The reason an unavailable button states to assistive technology and in its tooltip. */
  function reasonOf(button: HTMLElement): string | null {
    return button.getAttribute("aria-disabled") === "true"
      ? (document.getElementById(button.getAttribute("aria-describedby") ?? "")?.textContent ?? "")
      : null;
  }

  async function draftBanner(): Promise<HTMLElement> {
    const pane = await screen.findByTestId("SF-03-pane-estimate");
    return within(pane).findByTestId("SF-03-banner-estimate");
  }

  it("Submit for approval asks a variable consideration version for its constraint conclusion, and Save draft stores without it", async () => {
    serveWorkbench();
    const world = serveEstimates([rebate()], { [REBATE_ID]: [rebateVersion()] });
    open(`${LIST}/${REBATE_ID}`);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    fireEvent.click(await within(pane).findByRole("button", { name: "New estimate version" }));
    const drawer = await screen.findByRole("dialog", { name: /^New estimate version/ });
    type(within(drawer).getByLabelText("Effective date"), "30 Sep 2026");
    type(within(drawer).getByLabelText("Constrained amount (USD)"), "5,750.00");
    type(within(drawer).getByLabelText("Rationale"), "Forecast 1,450 units in the framework year.");
    const file = new File(["forecast"], "rebate-forecast-2026-09.pdf", { type: "application/pdf" });
    fireEvent.change(within(drawer).getByLabelText("Evidence"), { target: { files: [file] } });
    // The field is asked of the submission, so it is not marked optional.
    const conclusion = within(drawer).getByLabelText("Constraint conclusion");
    expect(conclusion.getAttribute("aria-required")).toBe("true");

    fireEvent.click(within(drawer).getByRole("button", { name: "Submit for approval" }));
    await waitFor(() =>
      expect(document.getElementById("field-constraintConclusion-error")?.textContent).toBe(
        REQUIRED,
      ),
    );
    expect(conclusion.getAttribute("aria-invalid")).toBe("true");
    expect(world.sent("POST", "/versions")).toHaveLength(0);

    // 04 §16.14 rev 1.241: the record is asked at the submission. The draft is stored without it.
    fireEvent.click(within(drawer).getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(world.sent("POST", "/preview")).toHaveLength(1));
    expect(world.sent("POST", "/versions")).toHaveLength(1);
    expect(world.sent("POST", "/api/v1/judgements")).toHaveLength(0);
    expect(world.sent("POST", "/submit")).toHaveLength(0);
    expect(document.getElementById("field-constraintConclusion-error")).toBeNull();
  });

  it("a new version starts without the record of the version it starts from and records its own", async () => {
    serveWorkbench();
    const world = serveEstimates([rebate()], {
      [REBATE_ID]: [rebateVersion({ version_no: 1, ...LINKED })],
    });
    const approved = world.versions.get(REBATE_ID)?.[0]?.id ?? "";
    world.judgements.set(approved, [constraintRecord(approved, { status: "REVIEWED" })]);
    open(`${LIST}/${REBATE_ID}`);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    fireEvent.click(await within(pane).findByRole("button", { name: "New estimate version" }));
    const drawer = await screen.findByRole("dialog", { name: /^New estimate version/ });
    // The record of version 1 is that version's: the new row names none (its `POST` sends none and the
    // API copies none), so the drawer does not say that one is linked and asks for a conclusion.
    expect(within(drawer).queryByText("A judgement record is linked.")).toBeNull();
    expect(within(drawer).queryByText(/JDG-000061/)).toBeNull();
    expect(world.recordReads).toEqual([]);
    type(within(drawer).getByLabelText("Effective date"), "30 Sep 2026");
    type(within(drawer).getByLabelText("Constrained amount (USD)"), "5,750.00");
    type(within(drawer).getByLabelText("Rationale"), "Forecast 1,450 units in the framework year.");
    type(
      within(drawer).getByLabelText("Constraint conclusion"),
      "A significant reversal is not probable: the threshold is expected to be met.",
    );
    fireEvent.click(within(drawer).getByRole("button", { name: "Save draft" }));

    await waitFor(() => expect(world.sent("POST", "/preview")).toHaveLength(1));
    const created = world.versions.get(REBATE_ID)?.[0];
    expect(world.sent("POST", "/versions")[0]?.body).not.toHaveProperty("judgement_record_id");
    expect(world.sent("POST", "/api/v1/judgements")[0]?.body).toMatchObject({
      topic: "CONSTRAINT",
      subject_type: "estimate_version",
      subject_id: created?.id,
      questionnaire: { estimate_key: "REBATE-DR-01", remote: false },
    });
    expect(world.sent("PATCH", created?.id ?? "")[0]?.body).toEqual({
      judgement_record_id: NEW_JUDGEMENT_ID,
    });
    expect(await within(drawer).findByText(/^JDG-000052 · /)).toBeTruthy();
    expect(within(drawer).queryByLabelText("Constraint conclusion")).toBeNull();
    // The record of the version it started from was never read: it is not this version's.
    expect(world.recordReads).not.toContain(CONSTRAINT_RECORD_ID);
  });

  it("a linked record that does not stand is shown with its status, and a new conclusion takes its place", async () => {
    serveWorkbench();
    const { world, id } = withSecond(LINKED, { record: "REJECTED" });
    open(`${LIST}/${REBATE_ID}`);

    const banner = await draftBanner();
    fireEvent.click(await within(banner).findByRole("button", { name: "Edit draft" }));
    const drawer = await screen.findByRole("dialog", { name: "Edit version 2 · REBATE-DR-01" });
    expect(
      await within(drawer).findByText(
        "JDG-000061 · A significant reversal is not probable. (Rejected)",
      ),
    ).toBeTruthy();
    // 04 §16.14 rev 1.241: a rejected record is not the record the submission asks for.
    const conclusion = within(drawer).getByLabelText("Constraint conclusion");
    fireEvent.click(within(drawer).getByRole("button", { name: "Submit for approval" }));
    await waitFor(() =>
      expect(document.getElementById("field-constraintConclusion-error")?.textContent).toBe(
        REQUIRED,
      ),
    );
    expect(world.sent("PATCH", id)).toHaveLength(0);

    type(conclusion, "The threshold is expected to be met: no significant reversal is probable.");
    fireEvent.click(within(drawer).getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(world.sent("POST", "/preview")).toHaveLength(1));
    // A new record is created, sent for review and linked in the place of the rejected one.
    expect(world.sent("POST", "/api/v1/judgements")).toHaveLength(1);
    expect(world.sent("POST", `${NEW_JUDGEMENT_ID}/submit`)).toHaveLength(1);
    expect(world.sent("PATCH", id).at(-1)?.body).toEqual({ judgement_record_id: NEW_JUDGEMENT_ID });
    expect(await within(drawer).findByText(/^JDG-000052 · /)).toBeTruthy();
    expect(within(drawer).queryByLabelText("Constraint conclusion")).toBeNull();
    // The rejected record is not changed: it stays as the version's history.
    expect(world.judgements.get(id)?.map((item) => [item.judgement_no, item.status])).toEqual([
      ["JDG-000052", "SUBMITTED"],
      ["JDG-000061", "REJECTED"],
    ]);
  });

  it("a record under a status this build does not name reads as the literal and does not stand", async () => {
    // No status is read through a message that may be missing: a literal a later API adds reads
    // as itself. E-57 `VOIDED`, the discard of a draft record (04 T-CON-19 rev 1.242), was such a
    // literal until SCREENS rev 1.66 gave it its word, "Void"; it does not stand either.
    for (const [status, word] of [
      ["ESCALATED", "ESCALATED"],
      ["VOIDED", "Void"],
    ] as const) {
      serveWorkbench();
      withSecond(LINKED, { record: status });
      open(`${LIST}/${REBATE_ID}`);

      const banner = await draftBanner();
      expect(
        reasonOf(await within(banner).findByRole("button", { name: "Submit for approval" })),
      ).toBe(CONCLUSION_FIRST);
      fireEvent.click(within(banner).getByRole("button", { name: "Edit draft" }));
      const drawer = await screen.findByRole("dialog", { name: "Edit version 2 · REBATE-DR-01" });
      expect(
        await within(drawer).findByText(
          `JDG-000061 · A significant reversal is not probable. (${word})`,
        ),
      ).toBeTruthy();
      expect(within(drawer).getByLabelText("Constraint conclusion")).toBeTruthy();
      cleanup();
      server.resetHandlers();
    }
  });

  it("without judgement.create the submission of a version that names no standing record is unavailable and says why", async () => {
    serveWorkbench();
    const world = serveEstimates([rebate()], { [REBATE_ID]: [rebateVersion()] });
    open(`${LIST}/${REBATE_ID}`, NO_JUDGEMENT);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    fireEvent.click(await within(pane).findByRole("button", { name: "New estimate version" }));
    const drawer = await screen.findByRole("dialog", { name: /^New estimate version/ });
    expect(within(drawer).queryByLabelText("Constraint conclusion")).toBeNull();
    expect(reasonOf(within(drawer).getByRole("button", { name: "Submit for approval" }))).toBe(
      NEEDS_PERMISSION,
    );
    // The draft is theirs to store: a holder of the permission completes it.
    type(within(drawer).getByLabelText("Effective date"), "30 Sep 2026");
    type(within(drawer).getByLabelText("Rationale"), "Forecast 1,450 units in the framework year.");
    fireEvent.click(within(drawer).getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(world.sent("POST", "/preview")).toHaveLength(1));
    expect(world.sent("POST", "/api/v1/judgements")).toHaveLength(0);
    cleanup();
    server.resetHandlers();

    // A draft that names a record sent for review is theirs to submit.
    serveWorkbench();
    withSecond(LINKED, { record: "SUBMITTED" });
    open(`${LIST}/${REBATE_ID}`, NO_JUDGEMENT);
    const banner = await draftBanner();
    fireEvent.click(await within(banner).findByRole("button", { name: "Edit draft" }));
    const edit = await screen.findByRole("dialog", { name: "Edit version 2 · REBATE-DR-01" });
    expect(
      await within(edit).findByText("JDG-000061 · A significant reversal is not probable."),
    ).toBeTruthy();
    expect(reasonOf(within(edit).getByRole("button", { name: "Submit for approval" }))).toBeNull();
  });

  it("the draft banner asks for the evidence first, then for the constraint conclusion, and neither of an attestation", async () => {
    const cases: readonly {
      readonly members: Partial<Parameters<typeof versionRow>[0]>;
      readonly options: { readonly record?: string; readonly evidence?: boolean };
      readonly reason: string | null;
    }[] = [
      { members: {}, options: { evidence: false }, reason: EVIDENCE_FIRST },
      { members: {}, options: {}, reason: CONCLUSION_FIRST },
      { members: LINKED, options: { record: "DRAFT" }, reason: CONCLUSION_FIRST },
      { members: LINKED, options: { record: "REJECTED" }, reason: CONCLUSION_FIRST },
      { members: LINKED, options: { record: "SUBMITTED" }, reason: null },
      { members: LINKED, options: { record: "REVIEWED" }, reason: null },
      // "Attest no change" stored the version and its submission failed: the API asks an attestation
      // for its reason alone (04 §16.14 rev 1.241), and refuses the flag itself where the values differ.
      {
        members: { parameters: { no_change_attestation: true } },
        options: { evidence: false },
        reason: null,
      },
    ];
    for (const item of cases) {
      serveWorkbench();
      const { world } = withSecond(item.members, item.options);
      open(`${LIST}/${REBATE_ID}`);
      const banner = await draftBanner();
      const submit = await within(banner).findByRole("button", { name: "Submit for approval" });
      expect([item.options, reasonOf(submit)]).toEqual([item.options, item.reason]);
      if ("parameters" in item.members) {
        // Neither read is made for an attestation.
        expect(world.recordReads).toEqual([]);
      }
      cleanup();
      server.resetHandlers();
    }
  });

  it("the pending banner says that the version's judgement record waits for review", async () => {
    const cases: readonly (readonly [string, string | null])[] = [
      ["SUBMITTED", "Judgement record JDG-000061 waits for review."],
      ["REVIEWED", null],
      [
        "REJECTED",
        "Judgement record JDG-000061 is not reviewed (Rejected). Withdraw the request to record a new conclusion.",
      ],
    ];
    for (const [status, sentence] of cases) {
      serveWorkbench();
      withSecond(
        { status: "SUBMITTED", approval_request_id: ESTIMATE_APPROVAL_ID, ...LINKED },
        { record: status },
      );
      open(`${LIST}/${REBATE_ID}`);
      const banner = await draftBanner();
      expect(await within(banner).findByText("Version 2 is waiting for approval.")).toBeTruthy();
      expect([
        status,
        within(banner).queryByText(/^Judgement record /)?.textContent ?? null,
      ]).toEqual([status, sentence]);
      cleanup();
      server.resetHandlers();
    }
  });

  it("the findings of a submission stand on the fields they are about, the evidence and the constraint conclusion", async () => {
    const EVIDENCE = "Attach the evidence of this estimate version before it is submitted.";
    const RECORD =
      "Name the CONSTRAINT judgement record of this element: a record of this contract for REBATE-DR-01, sent for review or reviewed.";
    serveWorkbench();
    const { world, id } = withSecond(LINKED, { record: "SUBMITTED" });
    world.refuse.submit = () => {
      // Between the drawer's read and the submission the reviewer rejected the record, and the file
      // of the attachment can no longer be read.
      world.judgements.set(id, [constraintRecord(id, { status: "REJECTED" })]);
      return problemResponse("validation-failed", 422, "Check the highlighted fields", {
        errors: [
          { field: null, rule_id: "ESTIMATE_EVIDENCE_REQUIRED", message: EVIDENCE },
          { field: "judgement_record_id", rule_id: "ESTIMATE_CONSTRAINT_RECORD", message: RECORD },
        ],
      });
    };
    open(`${LIST}/${REBATE_ID}`);

    const banner = await draftBanner();
    fireEvent.click(await within(banner).findByRole("button", { name: "Edit draft" }));
    const drawer = await screen.findByRole("dialog", { name: "Edit version 2 · REBATE-DR-01" });
    await within(drawer).findByText("JDG-000061 · A significant reversal is not probable.");
    fireEvent.click(within(drawer).getByRole("button", { name: "Submit for approval" }));

    await waitFor(() => expect(world.sent("POST", "/submit")).toHaveLength(1));
    // IMP-138 names no field: it stands under Evidence. IMP-140 names `judgement_record_id`: the
    // record is read again, no longer stands, and the finding stands on the field that replaces it.
    await waitFor(() =>
      expect(document.getElementById("field-evidence-error")?.textContent).toBe(EVIDENCE),
    );
    await waitFor(() =>
      expect(document.getElementById("field-constraintConclusion-error")?.textContent).toBe(RECORD),
    );
    expect(
      within(drawer).getByText("JDG-000061 · A significant reversal is not probable. (Rejected)"),
    ).toBeTruthy();
    // The banner of the refusal names the problem and repeats neither finding: each stands on its
    // field and, two fields being wrong, in the summary that links to them (DS-CMP-21).
    const refusal = within(drawer)
      .getByRole("heading", { name: "Check the highlighted fields" })
      .closest("[data-tone]");
    expect(refusal?.textContent).toMatch(/^Check the highlighted fieldsReference [0-9a-f-]+\.$/);
    expect(
      within(drawer)
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual([RECORD, EVIDENCE]);
    expect(world.versions.get(REBATE_ID)?.[0]?.status).toBe("DRAFT");
  });

  it("a record whose read fails is left to the API: the banner and the drawer hold nothing back", async () => {
    serveWorkbench();
    // The version names a record the stand-in does not hold: `GET /judgements/{id}` answers 404.
    const { world } = withSecond(LINKED);
    open(`${LIST}/${REBATE_ID}`);

    const banner = await draftBanner();
    expect(
      reasonOf(await within(banner).findByRole("button", { name: "Submit for approval" })),
    ).toBe(null);
    expect(world.recordReads).toEqual([CONSTRAINT_RECORD_ID]);
    fireEvent.click(within(banner).getByRole("button", { name: "Edit draft" }));
    const drawer = await screen.findByRole("dialog", { name: "Edit version 2 · REBATE-DR-01" });
    expect(await within(drawer).findByText("A judgement record is linked.")).toBeTruthy();
    expect(within(drawer).queryByLabelText("Constraint conclusion")).toBeNull();
    expect(
      reasonOf(within(drawer).getByRole("button", { name: "Submit for approval" })),
    ).toBeNull();
  });

  it("the banner waits for the record the open version names", async () => {
    serveWorkbench();
    withSecond(LINKED, { record: "SUBMITTED" });
    const read = hold(`/api/v1/judgements/${CONSTRAINT_RECORD_ID}`);
    open(`${LIST}/${REBATE_ID}`);

    const banner = await draftBanner();
    // The evidence is read and the record is not yet: the banner says nothing, its slot stays busy.
    await expect(within(banner).findByText(/^Version 2 /, {}, { timeout: 500 })).rejects.toThrow();
    expect(banner.querySelector("[aria-busy='true']")?.textContent).toBe("Loading Version status");
    read.release();
    expect(await within(banner).findByText("Version 2 is a draft.")).toBeTruthy();
    expect(
      reasonOf(within(banner).getByRole("button", { name: "Submit for approval" })),
    ).toBeNull();
  });

  it("an open version below the latest takes the banner and holds a new version back", async () => {
    // 04 §16.14 rev 1.241 (PRD ERR-93): a rejected version below the latest can be returned to draft
    // through the API while the latest one is not open.
    const cases: readonly (readonly [string, string, string])[] = [
      ["DRAFT", "Version 2 is a draft.", "Version 2 is a draft. Submit or discard it first."],
      [
        "SUBMITTED",
        "Version 2 is waiting for approval.",
        "Version 2 is waiting for approval. Withdraw the request or wait for the decision.",
      ],
    ];
    for (const [status, title, reason] of cases) {
      serveWorkbench();
      const world = serveEstimates([estimateRow()], {
        [EAC_ID]: [
          versionRow({ version_no: 3, status: "REJECTED", expected_total_amount: "850000.00" }),
          versionRow({
            version_no: 2,
            status: status as "DRAFT" | "SUBMITTED",
            expected_total_amount: "820000.00",
            approval_request_id: status === "SUBMITTED" ? ESTIMATE_APPROVAL_ID : null,
          }),
          versionRow({ version_no: 1, status: "APPROVED", expected_total_amount: "700000.00" }),
        ],
      });
      const second = world.versions.get(EAC_ID)?.[1]?.id ?? "";
      world.attachments.set(second, [evidenceFile(second, "eac-review-2026-09.xlsx")]);
      open(`${LIST}/${EAC_ID}`);

      const pane = await screen.findByTestId("SF-03-pane-estimate");
      const banner = await within(pane).findByTestId("SF-03-banner-estimate");
      expect(await within(banner).findByText(title)).toBeTruthy();
      // The rejected version 3 is not the open one: its banner and its "Edit draft" give way.
      expect(within(banner).queryByText(/^Version 3 /)).toBeNull();
      expect(reasonOf(within(pane).getByRole("button", { name: "New estimate version" }))).toBe(
        reason,
      );
      cleanup();
      server.resetHandlers();
    }
  });

  // SCREENS §8.3 (rev 1.66; PRD ERR-94, its second refusal): the approval of a pending version is
  // refused once its evidence is no longer attached, and the preparer learnt it from the approver.
  it("the pending banner says when the version's evidence is no longer attached, before what it says of the record, and not of an attestation", async () => {
    const GONE = "The evidence is no longer attached. Withdraw the request to attach it again.";
    const PENDING = { status: "SUBMITTED", approval_request_id: ESTIMATE_APPROVAL_ID } as const;
    const cases: readonly {
      readonly members: Partial<Parameters<typeof versionRow>[0]>;
      readonly options: { readonly record?: string; readonly evidence?: boolean };
      readonly sentences: readonly string[];
    }[] = [
      // The evidence is attached and the record reviewed: the title alone.
      { members: { ...PENDING, ...LINKED }, options: { record: "REVIEWED" }, sentences: [] },
      {
        members: { ...PENDING, ...LINKED },
        options: { record: "REVIEWED", evidence: false },
        sentences: [GONE],
      },
      // Both hold: the evidence first, the order of the draft's banner.
      {
        members: { ...PENDING, ...LINKED },
        options: { record: "SUBMITTED", evidence: false },
        sentences: [GONE, "Judgement record JDG-000061 waits for review."],
      },
      // An attestation is approved on its reason alone (04 §16.14 rev 1.241).
      {
        members: { ...PENDING, parameters: { no_change_attestation: true } },
        options: { evidence: false },
        sentences: [],
      },
    ];
    for (const item of cases) {
      serveWorkbench();
      withSecond(item.members, item.options);
      open(`${LIST}/${REBATE_ID}`);
      const banner = await draftBanner();
      const title = await within(banner).findByText("Version 2 is waiting for approval.");
      const said = Array.from(
        title.closest("[data-tone]")?.querySelectorAll("p") ?? [],
        (line) => line.textContent,
      );
      expect([item.options, said]).toEqual([item.options, item.sentences]);
      cleanup();
      server.resetHandlers();
    }
  });

  it("the pending banner waits for the read of the version's evidence", async () => {
    serveWorkbench();
    withSecond(
      { status: "SUBMITTED", approval_request_id: ESTIMATE_APPROVAL_ID, ...LINKED },
      { record: "REVIEWED", evidence: false },
    );
    const read = hold("/api/v1/attachments");
    open(`${LIST}/${REBATE_ID}`);

    const banner = await draftBanner();
    // The request and the record are read and the evidence is not yet: the slot stays busy rather
    // than state a version whose approval it would call unhindered.
    await expect(within(banner).findByText(/^Version 2 /, {}, { timeout: 500 })).rejects.toThrow();
    expect(banner.querySelector("[aria-busy='true']")?.textContent).toBe("Loading Version status");
    read.release();
    expect(await within(banner).findByText("Version 2 is waiting for approval.")).toBeTruthy();
    expect(
      within(banner).getByText(
        "The evidence is no longer attached. Withdraw the request to attach it again.",
      ),
    ).toBeTruthy();
  });

  // SCREENS §8.4 (rev 1.66; lane ACCT's reading of the attestation, ASC 606-10-32-11 and 32-12): the
  // reason says what was looked at, not only that the amount is unchanged.
  it("Attest no change says in the help of its rationale what belongs in it", async () => {
    serveWorkbench();
    serveEstimates([rebate()], { [REBATE_ID]: [rebateVersion()] });
    open(`${LIST}/${REBATE_ID}`);

    const pane = await screen.findByTestId("SF-03-pane-estimate");
    fireEvent.click(await within(pane).findByRole("button", { name: "Attest no change" }));
    const dialog = await screen.findByRole("dialog", {
      name: /^Attest no change for REBATE-DR-01/,
    });
    const rationale = within(dialog).getByLabelText(/^Rationale/);
    // The sentence is part of the field's description: the hint, then the minimum.
    expect(
      (rationale.getAttribute("aria-describedby") ?? "")
        .split(" ")
        .map((id) => document.getElementById(id)?.textContent),
    ).toEqual([
      "Say what you reviewed: the constraint factors, and that they stand as they were. Minimum 10 characters",
    ]);
  });

  // SCREENS §8.3 (rev 1.66; PRD SM-10 `DRAFT` → `VOIDED`; 04 API-R-33 rev 1.242): the version drawer
  // records the conclusion and sends it for review as two requests. A draft whose submission was
  // refused had no command once the drawer was closed.
  /** The records "Evidence" lists under version 2, each as the text of its line. */
  async function recordLines(): Promise<string[]> {
    const pane = await screen.findByTestId("SF-03-pane-estimate");
    const second = await within(pane).findByRole("region", { name: "Version 2" });
    return within(within(second).getByRole("list", { name: "Judgement records of version 2" }))
      .getAllByRole("listitem")
      .map((item) => item.textContent ?? "");
  }

  it("Evidence names each record's status in the shared words, and a draft record is discarded there", async () => {
    for (const [status, word] of [
      ["SUBMITTED", "Waiting for review"],
      ["REVIEWED", "Reviewed"],
      ["VOIDED", "Void"],
    ] as const) {
      serveWorkbench();
      withSecond(LINKED, { record: status });
      open(`${LIST}/${REBATE_ID}?pane=evidence`);
      // No command on a record that waits for review, is reviewed or is discarded already.
      expect(await recordLines()).toEqual([
        `JDG-000061A significant reversal is not probable.${word}`,
      ]);
      cleanup();
      server.resetHandlers();
    }

    serveWorkbench();
    const { world } = withSecond(LINKED, { record: "DRAFT" });
    open(`${LIST}/${REBATE_ID}?pane=evidence`);
    expect(await recordLines()).toEqual([
      "JDG-000061A significant reversal is not probable.DraftDiscard",
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Discard" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Discard this draft record?" });
    expect(dialog.getAttribute("data-testid")).toBe("SF-03-dialog-discard-record");
    expect(world.sent("POST", "/discard")).toHaveLength(0);
    fireEvent.click(within(dialog).getByRole("button", { name: "Discard" }));

    expect(await screen.findByText("Record JDG-000061 was discarded.")).toBeTruthy();
    expect(world.sent("POST", `/judgements/${CONSTRAINT_RECORD_ID}/discard`)[0]?.body).toBeNull();
    await waitFor(async () =>
      expect(await recordLines()).toEqual([
        "JDG-000061A significant reversal is not probable.Void",
      ]),
    );
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    // The draft version still names the record, which does not stand: its banner asks for a
    // conclusion, as before the discard.
    const banner = await draftBanner();
    expect(
      reasonOf(await within(banner).findByRole("button", { name: "Submit for approval" })),
    ).toBe(CONCLUSION_FIRST);
  });

  // SCREENS §8.3 (rev 1.74; PRD SM-10 rev 1.199; 04 rev 1.296): the discard takes a rejected record
  // as it takes a draft. Before, a rejected record of a version had no command on any screen.
  it("Evidence carries Discard on a rejected record, under a title that names it rejected", async () => {
    serveWorkbench();
    const { world } = withSecond(LINKED, { record: "REJECTED" });
    open(`${LIST}/${REBATE_ID}?pane=evidence`);
    expect(await recordLines()).toEqual([
      "JDG-000061A significant reversal is not probable.RejectedDiscard",
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Discard" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Discard this rejected record?",
    });
    expect(world.sent("POST", "/discard")).toHaveLength(0);
    fireEvent.click(within(dialog).getByRole("button", { name: "Discard" }));

    expect(await screen.findByText("Record JDG-000061 was discarded.")).toBeTruthy();
    expect(world.sent("POST", `/judgements/${CONSTRAINT_RECORD_ID}/discard`)).toHaveLength(1);
    await waitFor(async () =>
      expect(await recordLines()).toEqual([
        "JDG-000061A significant reversal is not probable.Void",
      ]),
    );
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
  });

  it("a draft record's line stands without the command for a member without judgement.create for the contract's entity, and on a view of an earlier known_at", async () => {
    const views: readonly (readonly [typeof NO_JUDGEMENT | undefined, string])[] = [
      [NO_JUDGEMENT, ""],
      // No command renders on a view of an earlier known_at.
      [undefined, "&known_at=2026-09-12T12%3A00%3A00Z"],
    ];
    for (const [me, extra] of views) {
      serveWorkbench();
      const { world } = withSecond(LINKED, { record: "DRAFT" });
      open(`${LIST}/${REBATE_ID}?pane=evidence${extra}`, me);
      expect(await recordLines()).toEqual([
        "JDG-000061A significant reversal is not probable.Draft",
      ]);
      expect(screen.queryByRole("button", { name: "Discard" })).toBeNull();
      expect(world.sent("POST", "/discard")).toHaveLength(0);
      cleanup();
      server.resetHandlers();
    }
  });
});
