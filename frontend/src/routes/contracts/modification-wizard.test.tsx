// @vitest-environment jsdom
// SF-07 Modification wizard (BUILD_SPEC CTR-27; SCREENS §7.3 to §7.8, §7.10; DESIGN_SYSTEM DS-CMP-18,
// DS-CMP-21; docs/dev-guide.md DG-FE-05; 04 API-R-31, §16.14 API-S-Modification; PRD BR-MOD-01,
// REQ-MOD-002, REQ-PLT-015): step "Change" creates the draft from a subscription action or the general
// form; the questionnaire counts an answer once it is stored and classifies again after every save; a
// treatment other than the proposal needs its judgement record; a save after a preview says that the
// preview is out of date; "Submit for approval" waits for the review of the override record and shows
// the API's refusal.
import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { RouteObject } from "react-router";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import { type Modification, modificationKey } from "../../lib/api/queries/modifications";
import {
  installMemoryStorage,
  preloadScreens,
  probeRoute,
  renderApp,
  signedInMe,
} from "../../test/app";
import { EAC_ID, estimateRow, REBATE_ID, serveEstimates, versionRow } from "../../test/estimates";
import {
  APPROVAL_ID,
  classifiedRow,
  JUDGEMENT_ID,
  judgementRecord,
  MODIFICATION_ID,
  modificationRow,
  NOT_DISCARDABLE,
  notDiscardable,
  OTHER_SSP_VERSION_ID,
  overrideRefusal,
  PREVIEW,
  previewedRow,
  recordsNotReviewed,
  REFERENCE,
  serveModification,
  serveOctoberOpen,
  SSP_VERSION_ID,
} from "../../test/modifications";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import {
  AVM_US,
  CONTEXT,
  CONTRACT_ID,
  K02,
  money,
  O1_ID,
  serveWorkbench,
  workbenchContract,
} from "../../test/workbench";

installMswServer();
installMemoryStorage();
// A step reads the contract, its obligations and the row before it renders.
configure({ asyncUtilTimeout: 5000 });

beforeAll(async () => {
  await preloadScreens(SCREEN_ROUTES, ["SF-07", "SF-07:detail"]);
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
const STALE = "The preview is out of date. Run it again before submitting.";
const OVERRIDE = "Record why this treatment differs from the proposal.";
// The sentences of the price test of K-02's added line: compared, and passed on the attestation.
const BELOW = "60,000.00 is below the range low 69,750.00 (US-LIST 2026-H1)";
const ATTESTED =
  "Attested by the preparer as priced at the standalone selling price. Price 60,000.00; SSP 69,750.00 to 85,250.00 (US-LIST 2026-H1).";
const DETAIL = `/contracts/${CONTRACT_ID}/modifications/${MODIFICATION_ID}`;
const CONFIRMED_O2 = { added_goods_distinct: true, priced_at_ssp: false };
const CONFIRMED_O1 = { remaining_goods_distinct_from_transferred: true };

// SF-07 and SF-07:detail as routed, and stand-ins for the screens the wizard links to.
const ROUTES: readonly RouteObject[] = [
  ...SCREEN_ROUTES.filter((route) => route.id === "SF-07" || route.id === "SF-07:detail"),
  probeRoute(
    "SF-03:modifications",
    "/contracts/:contractId/modifications",
    "contracts.modifications.documentTitle",
  ),
  probeRoute(
    "SF-03:estimate",
    "/contracts/:contractId/estimates/:estimateId",
    "contracts.estimates.documentTitle",
  ),
  probeRoute("SF-02", "/contracts", "contracts.list.title"),
];

function open(path: string, me = MAYA) {
  return renderApp(path, { me, screenRoutes: ROUTES });
}

function openStep(step: string, me = MAYA) {
  return open(`${DETAIL}?${CONTEXT}&step=${step}`, me);
}

function type(name: string | RegExp, value: string): HTMLElement {
  const input = screen.getByRole("textbox", { name });
  fireEvent.change(input, { target: { value } });
  return input;
}

/** Picks an option of a `components/form/Select` by its visible label. */
function select(name: string, option: string): void {
  const trigger = screen.getByRole("combobox", { name });
  fireEvent.click(trigger);
  const list = document.getElementById(trigger.getAttribute("aria-controls") ?? "");
  if (list === null) {
    throw new Error(`The select ${name} has no open list`);
  }
  fireEvent.mouseDown(within(list).getByRole("option", { name: option }));
}

function next(): HTMLElement {
  return screen.getByRole("button", { name: "Next" });
}

function question(name: string): HTMLElement {
  return screen.getByRole("radiogroup", { name });
}

/** The price question of the added line. */
function priced(): HTMLElement {
  return screen.getByRole("radiogroup", { name: /^Is the added price at SSP\?/ });
}

/** The answer a question shows: the label of its checked radio, or null. */
function answerOf(group: HTMLElement): string | null {
  const checked = within(group)
    .getAllByRole<HTMLInputElement>("radio")
    .find((radio) => radio.checked);
  return checked?.closest("label")?.textContent ?? null;
}

function confirmBox(key: string): HTMLInputElement {
  return screen.getByRole<HTMLInputElement>("checkbox", {
    name: `I confirm these answers for ${key}`,
  });
}

/** The text a sighted reader sees in each cell of a row: the visually hidden sign words are left out. */
function cellTexts(row: HTMLElement | undefined): string[] {
  return Array.from(row?.querySelectorAll("th, td") ?? [], (cell) => {
    const shown = cell.cloneNode(true) as HTMLElement;
    for (const hidden of shown.querySelectorAll(".sr-only")) {
      hidden.remove();
    }
    return (shown.textContent ?? "").replace(/\s+/g, " ").trim();
  });
}

function stepNames(): (string | null)[] {
  const steps = screen.getByRole("navigation", { name: "Modification steps" });
  return Array.from(steps.querySelectorAll("li .sr-only"), (item) => item.textContent);
}

describe("SF-07 the wizard of a draft", () => {
  it("next blocked until answers confirmed", async () => {
    serveWorkbench();
    const world = serveModification(modificationRow());
    const { router } = openStep("questionnaire");

    // The classification proposes the answers it can compute and stores none (BR-MOD-01).
    const priced = await screen.findByRole("radiogroup", { name: /^Is the added price at SSP\?/ });
    expect(answerOf(priced)).toBe("No");
    expect(
      await screen.findByText("60,000.00 is below the range low 69,750.00 (US-LIST 2026-H1)"),
    ).toBeTruthy();
    expect(answerOf(question("Are the added goods or services distinct?"))).toBe("Yes");
    expect(
      answerOf(
        question("Are the remaining goods or services distinct from those already transferred?"),
      ),
    ).toBe("Yes");
    expect(
      screen.getByText(
        "The obligation is a series of distinct goods or services; 35.5% of it has been transferred.",
      ),
    ).toBeTruthy();
    expect(screen.getAllByText("Prefilled")).toHaveLength(3);
    // One group per obligation, the added line first; each asks what applies to it.
    expect(screen.getAllByRole("heading", { level: 3 }).map((item) => item.textContent)).toEqual([
      "O2 AVM-SEAT-MO · 50 · 16 Sep 2026 to 31 Dec 2027",
      "O1 AVM-SEAT-MO · 100 · 01 Jan 2026 to 31 Dec 2027",
    ]);
    expect(within(screen.getByTestId("SF-07-group-O1")).getAllByRole("radiogroup")).toHaveLength(1);
    expect(screen.getByText("Proposed treatment: Prospective (ASC 606-10-25-13(a))")).toBeTruthy();
    expect(world.sent("POST", "/classify")).toHaveLength(1);
    expect(world.row.questionnaire).toEqual({});

    // Nothing is confirmed: "Next" says what blocks it and does not go on.
    expect(screen.getByTestId("SF-07-blocked").textContent).toBe(
      "Confirm every answer to continue.",
    );
    expect(next().getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(next());
    expect(router.state.location.search).toContain("step=questionnaire");
    expect(stepNames()[1]).toBe("Step 2 of 5, Questionnaire, 0 answers confirmed");

    // Confirming a group stores its answers as they read, then the classification runs again.
    fireEvent.click(confirmBox("O2"));
    await waitFor(() => expect(world.sent("POST", "/classify")).toHaveLength(2));
    expect(world.sent("PATCH", MODIFICATION_ID)[0]?.body).toEqual({
      questionnaire: { O2: CONFIRMED_O2 },
      chosen_treatments: {},
    });
    await waitFor(() => expect(confirmBox("O2").checked).toBe(true));
    // One group is still open.
    expect(confirmBox("O1").checked).toBe(false);
    expect(screen.getByTestId("SF-07-blocked").textContent).toBe(
      "Confirm every answer to continue.",
    );
    expect(next().getAttribute("aria-disabled")).toBe("true");
    expect(screen.getAllByText("Prefilled")).toHaveLength(1);

    fireEvent.click(confirmBox("O1"));
    await waitFor(() => expect(screen.queryByTestId("SF-07-blocked")).toBeNull());
    expect(world.sent("PATCH", MODIFICATION_ID)[1]?.body).toEqual({
      questionnaire: { O2: CONFIRMED_O2, O1: CONFIRMED_O1 },
      chosen_treatments: {},
    });
    expect(world.sent("POST", "/classify")).toHaveLength(3);
    expect(next().getAttribute("aria-disabled")).toBeNull();
    expect(screen.queryByText("Prefilled")).toBeNull();
    expect(stepNames()[1]).toBe("Step 2 of 5, Questionnaire, 3 answers confirmed");

    // Changing an answer stores it and classifies again: the proposal follows the answer, and the
    // default of the classification before it does not stand as a departure.
    fireEvent.click(
      within(question("Is the added price at SSP?")).getByRole("radio", { name: "Yes" }),
    );
    expect(
      await screen.findByText("Proposed treatment: Separate contract (ASC 606-10-25-12)"),
    ).toBeTruthy();
    expect(world.sent("POST", "/classify")).toHaveLength(4);
    expect(world.sent("PATCH", MODIFICATION_ID)[2]?.body).toEqual({
      questionnaire: {
        O2: { added_goods_distinct: true, priced_at_ssp: true },
        O1: CONFIRMED_O1,
      },
      chosen_treatments: {},
    });
    expect(world.row.chosen_treatments).toEqual({ O2: "SEPARATE_CONTRACT" });
    expect(screen.queryByText("Treatment override")).toBeNull();

    await waitFor(() => expect(next().getAttribute("aria-busy")).toBeNull());
    fireEvent.click(next());
    await waitFor(() => expect(router.state.location.search).toContain("step=treatment"));
    // Step 3 shows the SSP basis with the range of the price test the row states (SCREENS §7.6).
    const treatments = await screen.findByRole("table", { name: "Treatment by obligation" });
    // The step is a search parameter: its heading takes the focus, as a page heading does on a route.
    expect(document.activeElement).toBe(
      screen.getByRole("heading", { level: 2, name: "Treatment" }),
    );
    expect(
      await within(treatments).findByText("US-LIST 2026-H1 · 69,750.00 to 85,250.00"),
    ).toBeTruthy();
    expect(within(treatments).getAllByRole("rowheader")).toHaveLength(1);
  });

  it("a stored answer stays confirmed when a classification names it as a proposal, and the next save carries it", async () => {
    serveWorkbench();
    const world = serveModification(modificationRow());
    // The classification reports the price test beside the answer the row holds:
    // `prefill_reasons.O2.priced_at_ssp` names an answer that is stored.
    world.priceTestAlways = true;
    openStep("questionnaire");
    const settled = () => waitFor(() => expect(next().getAttribute("aria-busy")).toBeNull());

    await screen.findByRole("radiogroup", { name: /^Is the added price at SSP\?/ });
    expect(screen.getAllByText("Prefilled")).toHaveLength(3);
    fireEvent.click(confirmBox("O2"));
    await waitFor(() => expect(world.sent("POST", "/classify")).toHaveLength(2));
    await settled();
    expect(world.row.questionnaire).toEqual({ O2: CONFIRMED_O2 });
    // The row holds both answers of O2, so the group stays confirmed and neither reads "Prefilled".
    expect(confirmBox("O2").checked).toBe(true);
    expect(screen.getAllByText("Prefilled")).toHaveLength(1);
    expect(stepNames()[1]).toBe("Step 2 of 5, Questionnaire, 2 answers confirmed");

    // The next save sends every answer the row holds.
    fireEvent.click(confirmBox("O1"));
    await waitFor(() => expect(world.sent("POST", "/classify")).toHaveLength(3));
    await settled();
    expect(world.sent("PATCH", MODIFICATION_ID)[1]?.body).toEqual({
      questionnaire: { O2: CONFIRMED_O2, O1: CONFIRMED_O1 },
      chosen_treatments: {},
    });
    expect(confirmBox("O2").checked).toBe(true);
    expect(confirmBox("O1").checked).toBe(true);
    expect(screen.queryByTestId("SF-07-blocked")).toBeNull();
    expect(next().getAttribute("aria-disabled")).toBeNull();

    // An answer the preparer changed stays as given, whatever the price test still proposes.
    fireEvent.click(within(priced()).getByRole("radio", { name: "Yes" }));
    expect(
      await screen.findByText("Proposed treatment: Separate contract (ASC 606-10-25-12)"),
    ).toBeTruthy();
    await settled();
    expect(world.row.questionnaire).toEqual({
      O2: { added_goods_distinct: true, priced_at_ssp: true },
      O1: CONFIRMED_O1,
    });
    expect(answerOf(priced())).toBe("Yes");
    expect(confirmBox("O2").checked).toBe(true);
    expect(screen.queryByText("Prefilled")).toBeNull();
  });

  // 04 §16.14 rev 1.250 `price_tests` (item MOD-PRICE-TEST-FACT-1): the engine's price test of an
  // added line is a member of the row, stated whatever the preparer answered. SCREENS §7.5, §7.6.
  it("the price test of a stored answer of No stays under the question and beside the SSP version", async () => {
    serveWorkbench();
    // A draft opened after its answers were confirmed: no proposal names the price question.
    const world = serveModification(classifiedRow());
    const { router } = openStep("questionnaire");

    await screen.findByRole("radiogroup", { name: /^Is the added price at SSP\?/ });
    expect(answerOf(priced())).toBe("No");
    expect(confirmBox("O2").checked).toBe(true);
    // The sentence of the price test is a fact beside the stored answer, not a proposal.
    expect(await within(priced()).findByText(BELOW)).toBeTruthy();
    expect(screen.queryByText("Prefilled")).toBeNull();
    expect(world.sent("POST", "/classify")).toHaveLength(0);

    fireEvent.click(next());
    await waitFor(() => expect(router.state.location.search).toContain("step=treatment"));
    const treatments = await screen.findByRole("table", { name: "Treatment by obligation" });
    expect(
      await within(treatments).findByText("US-LIST 2026-H1 · 69,750.00 to 85,250.00"),
    ).toBeTruthy();
    expect(world.sent("POST", "/classify")).toHaveLength(0);
  });

  it("a stored answer of Yes reads as attested with the price and the range, and the screen concludes nothing", async () => {
    serveWorkbench();
    const world = serveModification(modificationRow());
    const { router } = openStep("questionnaire");
    const settled = () => waitFor(() => expect(next().getAttribute("aria-busy")).toBeNull());

    // Proposed: the engine compared the price with the range.
    await screen.findByRole("radiogroup", { name: /^Is the added price at SSP\?/ });
    expect(await within(priced()).findByText(BELOW)).toBeTruthy();
    fireEvent.click(within(priced()).getByRole("radio", { name: "Yes" }));
    expect(
      await screen.findByText("Proposed treatment: Separate contract (ASC 606-10-25-12)"),
    ).toBeTruthy();
    await settled();

    // Answered Yes: the engine passed on the attestation and compared nothing. The row states the
    // two figures all the same, and the screen says no more than that.
    expect(world.row.price_tests).toEqual({
      O2: {
        value: true,
        reason_key: "modifications.prefill.priced_at_ssp.attested",
        params: { price: "60000", ssp_version_key: "US-LIST@v1", low: "69750", high: "85250" },
      },
    });
    expect(answerOf(priced())).toBe("Yes");
    expect(await within(priced()).findByText(ATTESTED)).toBeTruthy();
    expect(screen.queryByText(BELOW)).toBeNull();
    expect(screen.queryByText(/below the range|above the range|within the range/)).toBeNull();

    // The attestation makes the added goods a contract of their own: O2 alone is asked.
    fireEvent.click(confirmBox("O2"));
    await waitFor(() => expect(screen.queryByTestId("SF-07-blocked")).toBeNull());
    await settled();
    expect(within(priced()).getByText(ATTESTED)).toBeTruthy();
    fireEvent.click(next());
    await waitFor(() => expect(router.state.location.search).toContain("step=treatment"));
    const treatments = await screen.findByRole("table", { name: "Treatment by obligation" });
    expect(
      await within(treatments).findByText("US-LIST 2026-H1 · 69,750.00 to 85,250.00"),
    ).toBeTruthy();
  });

  it("an attestation states the point of an SSP entry, or the price alone where no entry resolves", async () => {
    const attested = (params: Readonly<Record<string, string>>) =>
      classifiedRow({
        questionnaire: {
          O1: CONFIRMED_O1,
          O2: { added_goods_distinct: true, priced_at_ssp: true },
        },
        price_tests: {
          O2: {
            value: true,
            reason_key: "modifications.prefill.priced_at_ssp.attested",
            params: { price: "60000", ...params },
          },
        },
      });
    serveWorkbench();
    serveModification(
      attested({ ssp_version_key: "US-LIST@v1", point: "77500", point_tolerance_pct: "5" }),
    );
    const point = openStep("questionnaire");
    await screen.findByRole("radiogroup", { name: /^Is the added price at SSP\?/ });
    expect(
      await within(priced()).findByText(
        "Attested by the preparer as priced at the standalone selling price. Price 60,000.00; SSP 77,500.00 (US-LIST 2026-H1).",
      ),
    ).toBeTruthy();
    fireEvent.click(next());
    await waitFor(() => expect(point.router.state.location.search).toContain("step=treatment"));
    expect(
      await within(
        await screen.findByRole("table", { name: "Treatment by obligation" }),
      ).findByText("US-LIST 2026-H1 · 77,500.00"),
    ).toBeTruthy();
    cleanup();

    serveWorkbench();
    serveModification(attested({ ssp_version_key: "" }));
    const none = openStep("questionnaire");
    await screen.findByRole("radiogroup", { name: /^Is the added price at SSP\?/ });
    expect(
      await within(priced()).findByText(
        "Attested by the preparer as priced at the standalone selling price. Price 60,000.00; no approved SSP applies to the added goods or services at the modification date.",
      ),
    ).toBeTruthy();
    fireEvent.click(next());
    await waitFor(() => expect(none.router.state.location.search).toContain("step=treatment"));
    const treatments = await screen.findByRole("table", { name: "Treatment by obligation" });
    expect(await within(treatments).findByText("US-LIST 2026-H1")).toBeTruthy();
    expect(within(treatments).queryByText(/·/)).toBeNull();
  });

  it("a row that states no price test shows no sentence and the SSP version alone", async () => {
    serveWorkbench();
    // `{}`: a row that is not classified or was edited since, one classified before the member
    // existed, a line the engine does not test.
    const world = serveModification(classifiedRow({ price_tests: {} }));
    const { router } = openStep("questionnaire");

    await screen.findByRole("radiogroup", { name: /^Is the added price at SSP\?/ });
    expect(answerOf(priced())).toBe("No");
    await waitFor(() => expect(next().getAttribute("aria-busy")).toBeNull());
    expect(within(priced()).queryByText(BELOW)).toBeNull();
    expect(within(priced()).queryByText(/60,000\.00/)).toBeNull();
    expect(world.sent("POST", "/classify")).toHaveLength(0);

    fireEvent.click(next());
    await waitFor(() => expect(router.state.location.search).toContain("step=treatment"));
    const treatments = await screen.findByRole("table", { name: "Treatment by obligation" });
    expect(await within(treatments).findByText("US-LIST 2026-H1")).toBeTruthy();
    expect(within(treatments).queryByText(/69,750\.00/)).toBeNull();
  });

  it("beside an SSP version the preparer named, the range of another version is not printed and the sentence names the tested one by its key", async () => {
    // "Use another approved SSP version" (REQ-SSP-006) names the version of the allocation. The
    // price test read the version of the modification date (`ssp_version_key` US-LIST@v1): its
    // figures are not those of the named version, US-LIST@v2 "2026-H2".
    const named = (versionId: string) =>
      classifiedRow({
        ssp_basis: {
          O2: {
            ssp_book_version_id: versionId,
            is_override: true,
            justification: "Approved after the order date.",
          },
        },
      });
    serveWorkbench();
    serveModification(named(OTHER_SSP_VERSION_ID));
    const { router } = openStep("treatment");

    const treatments = await screen.findByRole("table", { name: "Treatment by obligation" });
    // The cell "SSP basis" of O2 (the fourth): the named version's label, and nothing beside it.
    const basis = () =>
      cellTexts(
        within(treatments)
          .getAllByRole("row")
          .find((row) => within(row).queryByRole("rowheader")?.textContent?.startsWith("O2")),
      )[3];
    await waitFor(() => expect(basis()).toBe("US-LIST 2026-H2"));
    expect(within(treatments).queryByText(/69,750\.00/)).toBeNull();
    // The label of the named version is read by now: the sentence does not take it either.
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    await waitFor(() => expect(router.state.location.search).toContain("step=questionnaire"));
    await screen.findByRole("radiogroup", { name: /^Is the added price at SSP\?/ });
    expect(
      within(priced()).getByText("60,000.00 is below the range low 69,750.00 (US-LIST v1)"),
    ).toBeTruthy();
    expect(screen.queryByText(/\(US-LIST 2026-H2\)/)).toBeNull();
    cleanup();

    // The named version is the one the test read: the range stands beside it.
    serveWorkbench();
    serveModification(named(SSP_VERSION_ID));
    openStep("treatment");
    expect(
      await within(
        await screen.findByRole("table", { name: "Treatment by obligation" }),
      ).findByText("US-LIST 2026-H1 · 69,750.00 to 85,250.00"),
    ).toBeTruthy();
  });

  it("a draft opened with its proposals keeps the range on step 3 once its answers are confirmed", async () => {
    serveWorkbench();
    // The draft as an earlier visit left it, classified and unanswered: its read carries the
    // proposals of all three questions (04 T-CON-06 `classification`, rev 1.210), so this visit
    // classifies nothing on opening; a classification names a question no more once its answer is
    // stored (rev 1.235), and the price test stays a member of the row (rev 1.250). This is the
    // path of the e2e row "SF-07:detail maya", red on main while the range was read from a proposal.
    const world = serveModification(
      classifiedRow({
        questionnaire: {},
        proposal_detail: { "class[O1]": "D", "class[O2]": "D", "ssp_version[O2]": "US-LIST@v1" },
        prefill_reasons: {
          O2: {
            added_goods_distinct: {
              value: true,
              reason_key: "modifications.prefill.added_goods_distinct.new_distinct",
              params: {},
            },
            priced_at_ssp: {
              value: false,
              reason_key: "modifications.prefill.priced_at_ssp.below_range",
              params: {
                price: "60000",
                ssp_version_key: "US-LIST@v1",
                low: "69750",
                high: "85250",
              },
            },
          },
          O1: {
            remaining_goods_distinct_from_transferred: {
              value: true,
              reason_key: "modifications.prefill.remaining_goods_distinct_from_transferred.series",
              params: { progress: "0.354794520547945205", progress_measure: "TIME_ELAPSED" },
            },
          },
        },
      }),
    );
    const { router } = openStep("questionnaire");

    await screen.findByRole("radiogroup", { name: /^Is the added price at SSP\?/ });
    expect(screen.getAllByText("Prefilled")).toHaveLength(3);
    expect(world.sent("POST", "/classify")).toHaveLength(0);
    fireEvent.click(confirmBox("O2"));
    await waitFor(() => expect(confirmBox("O2").checked).toBe(true));
    fireEvent.click(confirmBox("O1"));
    await waitFor(() => expect(screen.queryByTestId("SF-07-blocked")).toBeNull());
    // Both classifications of this visit ran after the price question was answered: no proposal
    // names it, and the sentence stays under the stored answer.
    expect(world.sent("POST", "/classify")).toHaveLength(2);
    // 04 §16.14 rev 1.286: nothing is proposed, and the row still states its classification.
    expect(world.row.prefill_reasons).toEqual({});
    expect(world.row.proposal_detail).toEqual({
      "class[O1]": "D",
      "class[O2]": "D",
      "ssp_version[O2]": "US-LIST@v1",
    });
    expect(screen.queryByText("Prefilled")).toBeNull();
    expect(await within(priced()).findByText(BELOW)).toBeTruthy();

    await waitFor(() => expect(next().getAttribute("aria-busy")).toBeNull());
    fireEvent.click(next());
    await waitFor(() => expect(router.state.location.search).toContain("step=treatment"));
    const treatments = await screen.findByRole("table", { name: "Treatment by obligation" });
    expect(
      await within(treatments).findByText("US-LIST 2026-H1 · 69,750.00 to 85,250.00"),
    ).toBeTruthy();
  });

  it("override banner", async () => {
    serveWorkbench();
    const world = serveModification(classifiedRow());
    const { router } = openStep("treatment");

    const table = await screen.findByRole("table", { name: "Treatment by obligation" });
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual(["Obligation", "Proposed treatment", "Chosen treatment", "SSP basis", "Override"]);
    const chosen = within(table).getByRole<HTMLSelectElement>("combobox", {
      name: "Chosen treatment for O1",
    });
    expect(chosen.value).toBe("PROSPECTIVE");
    // The guided route: the legacy presets are not offered (POL-100).
    expect(Array.from(chosen.options, (option) => option.textContent)).toEqual([
      "Separate contract (ASC 606-10-25-12)",
      "Prospective (ASC 606-10-25-13(a))",
      "Cumulative catch-up (ASC 606-10-25-13(b))",
      "Mixed (ASC 606-10-25-13(c))",
    ]);
    // The classified row states the price test of its added line (04 §16.14 rev 1.250).
    expect(await within(table).findByText("US-LIST 2026-H1 · 69,750.00 to 85,250.00")).toBeTruthy();
    expect(screen.queryByTestId("SF-07-banner-override")).toBeNull();
    expect(screen.queryByText("Treatment override")).toBeNull();
    expect(next().getAttribute("aria-disabled")).toBeNull();

    // A treatment other than the proposal: the banner, the header chip, and "Next" is blocked.
    fireEvent.change(chosen, { target: { value: "CUMULATIVE_CATCH_UP" } });
    const banner = await screen.findByTestId("SF-07-banner-override");
    expect(banner.getAttribute("role")).toBe("status");
    expect(within(banner).getByText(OVERRIDE)).toBeTruthy();
    expect(screen.getByText("Treatment override")).toBeTruthy();
    expect(screen.getByTestId("SF-07-blocked").textContent).toBe(
      "Record the judgement to continue.",
    );
    expect(next().getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(next());
    expect(world.sent("PATCH", MODIFICATION_ID)).toHaveLength(0);

    // "Record judgement": the record is created, submitted for review and linked with the choice.
    fireEvent.click(within(banner).getByRole("button", { name: "Record judgement" }));
    const drawer = await screen.findByRole("dialog", { name: "Record judgement" });
    expect(within(drawer).getByText("Modification treatment override")).toBeTruthy();
    fireEvent.click(within(drawer).getByRole("button", { name: "Save and submit for review" }));
    expect(await within(drawer).findByText("Enter the rationale.")).toBeTruthy();
    expect(world.sent("POST", "/judgements")).toHaveLength(0);
    fireEvent.change(within(drawer).getByRole("textbox", { name: "Conclusion" }), {
      target: { value: "The added seats reprice the remaining seats." },
    });
    fireEvent.change(within(drawer).getByRole("textbox", { name: "Rationale" }), {
      target: { value: "The discount applies to the whole term." },
    });
    fireEvent.click(within(drawer).getByRole("button", { name: "Save and submit for review" }));

    await waitFor(() => expect(world.sent("POST", "/classify")).toHaveLength(1));
    expect(world.sent("POST", "/judgements")[0]?.body).toEqual({
      topic: "MODIFICATION_TREATMENT_OVERRIDE",
      subject_type: "modification",
      subject_id: MODIFICATION_ID,
      conclusion: "The added seats reprice the remaining seats.",
      rationale: "The discount applies to the whole term.",
      codification_refs: [],
    });
    expect(world.sent("POST", `/judgements/${JUDGEMENT_ID}/submit`)).toHaveLength(1);
    expect(world.sent("PATCH", MODIFICATION_ID)[0]?.body).toEqual({
      chosen_treatments: { O1: "CUMULATIVE_CATCH_UP", O2: "PROSPECTIVE" },
      ssp_basis: {},
      judgement_record_id: JUDGEMENT_ID,
    });

    // The record exists: the banner names it — a record sent for review reads "Waiting for
    // review" (SCREENS §0.8, rev 1.66) — and "Next" goes on.
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(
      await within(await screen.findByTestId("SF-07-banner-override")).findByText(
        "Judgement record JDG-000012: Waiting for review.",
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Record judgement" })).toBeNull();
    expect(screen.queryByTestId("SF-07-blocked")).toBeNull();
    expect(screen.getByText("Treatment override")).toBeTruthy();
    expect(
      screen.getByRole<HTMLSelectElement>("combobox", { name: "Chosen treatment for O1" }).value,
    ).toBe("CUMULATIVE_CATCH_UP");
    await waitFor(() => expect(next().getAttribute("aria-busy")).toBeNull());
    expect(next().getAttribute("aria-disabled")).toBeNull();
    fireEvent.click(next());
    await waitFor(() => expect(router.state.location.search).toContain("step=preview"));
    expect(await screen.findByRole("region", { name: "Impact summary (USD)" })).toBeTruthy();
  });

  it("a judgement record whose create gets no answer goes out again under the key it had", async () => {
    // DG-FE-05 rev 1.156 (item W-23): the drawer's commands take their keys from the drawer. The API
    // replays the record it created when its answer was lost; a key made per call created a second.
    serveWorkbench();
    const world = serveModification(classifiedRow());
    const keys: (string | null)[] = [];
    server.use(
      http.post(apiUrl("/api/v1/judgements"), ({ request }) => {
        keys.push(request.headers.get("Idempotency-Key"));
        // The first create gets no answer; the next one reaches the world's own handler.
        return keys.length === 1 ? HttpResponse.error() : undefined;
      }),
    );
    openStep("treatment");
    const table = await screen.findByRole("table", { name: "Treatment by obligation" });
    fireEvent.change(within(table).getByRole("combobox", { name: "Chosen treatment for O1" }), {
      target: { value: "CUMULATIVE_CATCH_UP" },
    });
    const banner = await screen.findByTestId("SF-07-banner-override");
    fireEvent.click(within(banner).getByRole("button", { name: "Record judgement" }));
    const drawer = await screen.findByRole("dialog", { name: "Record judgement" });
    fireEvent.change(within(drawer).getByRole("textbox", { name: "Conclusion" }), {
      target: { value: "The added seats reprice the remaining seats." },
    });
    fireEvent.change(within(drawer).getByRole("textbox", { name: "Rationale" }), {
      target: { value: "The discount applies to the whole term." },
    });
    const press = within(drawer).getByRole("button", { name: "Save and submit for review" });

    fireEvent.click(press);
    await waitFor(() => expect(keys).toHaveLength(1));
    expect(keys[0]).toMatch(/^[0-9a-f-]{36}$/);
    // No answer: the drawer says so and keeps its input; nothing reached the API's own handler.
    expect(await within(drawer).findByRole("alert")).toBeTruthy();
    expect(world.sent("POST", "/judgements")).toHaveLength(0);

    await waitFor(() => expect(press.getAttribute("aria-busy")).toBeNull());
    fireEvent.click(press);
    await waitFor(() =>
      expect(world.sent("POST", `/judgements/${JUDGEMENT_ID}/submit`)).toHaveLength(1),
    );
    expect(keys).toHaveLength(2);
    expect(keys[1]).toBe(keys[0]);
    expect(world.sent("POST", "/judgements")).toHaveLength(1);
  });

  it("stale preview warning", async () => {
    // Step 2: a changed answer clears the stored preview.
    serveWorkbench();
    let world = serveModification(previewedRow());
    let rendered = openStep("questionnaire");
    await screen.findByRole("radiogroup", { name: "Is the added price at SSP?" });
    expect(screen.queryByText(STALE)).toBeNull();
    // A stored preview says the row is classified as it stands: nothing is classified on opening.
    expect(world.sent("POST", "/classify")).toHaveLength(0);
    expect(stepNames()[3]).toBe("Step 4 of 5, Impact preview, Catch-up 0.00");

    fireEvent.click(confirmBox("O1"));
    expect(await screen.findByText(STALE)).toBeTruthy();
    expect(world.row.impact_preview).toBeNull();
    // The preview cannot run before the steps ahead of it are done.
    const run = () => screen.getByRole("button", { name: "Run preview" });
    await waitFor(() => expect(confirmBox("O1").checked).toBe(false));
    expect(run().getAttribute("aria-disabled")).toBe("true");
    await waitFor(() => expect(confirmBox("O1").disabled).toBe(false));
    fireEvent.click(confirmBox("O1"));
    await waitFor(() => expect(run().getAttribute("aria-disabled")).toBeNull());
    expect(screen.getByText(STALE)).toBeTruthy();

    // "Run preview" opens step 4, which runs it; the warning goes when the row holds a preview again.
    fireEvent.click(run());
    await waitFor(() => expect(rendered.router.state.location.search).toContain("step=preview"));
    const strip = await screen.findByRole("region", { name: "Impact summary (USD)" });
    expect(within(strip).getByText("300,000.00")).toBeTruthy();
    expect(within(strip).getByText("Before 240,000.00")).toBeTruthy();
    expect(world.sent("POST", "/preview")).toHaveLength(1);
    await waitFor(() => expect(screen.queryByText(STALE)).toBeNull());
    cleanup();
    server.resetHandlers();

    // Step 3: another SSP version for the added line, saved by "Next".
    serveWorkbench();
    world = serveModification(previewedRow());
    world.previewEnds = "RUNNING";
    rendered = openStep("treatment");
    await screen.findByRole("table", { name: "Treatment by obligation" });
    expect(screen.queryByText(STALE)).toBeNull();
    fireEvent.click(
      await screen.findByRole("checkbox", { name: "Use another approved SSP version for O2" }),
    );
    fireEvent.change(screen.getByRole("combobox", { name: "SSP version for O2" }), {
      target: { value: OTHER_SSP_VERSION_ID },
    });
    fireEvent.change(screen.getByRole("textbox", { name: "Justification for O2" }), {
      target: { value: "The second-half list applies to seats added after 01 Jul 2026." },
    });
    fireEvent.click(next());
    expect(await screen.findByText(STALE)).toBeTruthy();
    expect(world.sent("PATCH", MODIFICATION_ID)[0]?.body).toEqual({
      chosen_treatments: { O1: "PROSPECTIVE", O2: "PROSPECTIVE" },
      ssp_basis: {
        O2: {
          ssp_book_version_id: OTHER_SSP_VERSION_ID,
          is_override: true,
          justification: "The second-half list applies to seats added after 01 Jul 2026.",
        },
      },
    });
    // Step 4 is already running the new preview, so the warning offers no second way to run it.
    await waitFor(() => expect(rendered.router.state.location.search).toContain("step=preview"));
    expect(await screen.findByRole("progressbar", { name: "Calculating preview" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Run preview" })).toBeNull();
    expect(screen.getByText(STALE)).toBeTruthy();
    cleanup();
    server.resetHandlers();

    // Step 1: a changed scope description, saved by "Next".
    serveWorkbench();
    world = serveModification(previewedRow());
    rendered = openStep("change");
    const scope = await screen.findByRole("textbox", { name: /^Scope description/ });
    expect(screen.queryByText(STALE)).toBeNull();
    fireEvent.change(scope, {
      target: { value: "Marrowby adds 50 seats for the remaining term." },
    });
    fireEvent.click(next());
    expect(await screen.findByText(STALE)).toBeTruthy();
    await waitFor(() =>
      expect(rendered.router.state.location.search).toContain("step=questionnaire"),
    );
    expect(world.sent("PATCH", MODIFICATION_ID)[0]?.body).toMatchObject({
      kind: "CO_TERM",
      reference: REFERENCE,
      effective_date: "2026-09-16",
      rationale: "Marrowby adds 50 seats for the remaining term.",
      chosen_treatments: {},
    });
    expect(world.sent("POST", "/classify")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Run preview" })).toBeTruthy();
  });

  it("opens on the first step that is not done and names the step in the URL", async () => {
    serveWorkbench();
    const world = serveModification(classifiedRow());
    // SCREENS §7.7: entering step 4 runs the preview of a row that holds none. The job is held here,
    // so the stepper is read while the preview runs and again once the row holds it; read without
    // holding it, the assertion below raced the stand-in's answer.
    world.previewEnds = "RUNNING";
    // The submit step is asked for; the preview before it is not done.
    const { router } = openStep("submit");

    expect(await screen.findByRole("heading", { level: 2, name: "Impact preview" })).toBeTruthy();
    await waitFor(() => expect(router.state.location.search).toContain("step=preview"));
    expect(await screen.findByRole("progressbar", { name: "Calculating preview" })).toBeTruthy();
    expect(world.sent("POST", "/preview")).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1, name: "New modification" })).toBeTruthy();
    expect(screen.getByTestId("SF-07-identifier").textContent).toBe(REFERENCE);
    expect(
      Array.from(
        screen.getByRole("navigation", { name: "Breadcrumb" }).querySelectorAll("li"),
        (item) => item.textContent?.replace("/", "").trim(),
      ),
    ).toEqual(["Contracts", K02, "New modification"]);
    // Completed steps link back; the current one carries aria-current, later ones are not links.
    const steps = screen.getByRole("navigation", { name: "Modification steps" });
    expect(stepNames()).toEqual([
      "Step 1 of 5, Change, Co-term · 16 Sep 2026",
      "Step 2 of 5, Questionnaire, 3 answers confirmed",
      "Step 3 of 5, Treatment, Prospective (ASC 606-10-25-13(a))",
      "Step 4 of 5, Impact preview, current",
      "Step 5 of 5, Submit, not started",
    ]);
    expect(
      within(steps)
        .getAllByRole("link")
        .map((link) =>
          new URL(link.getAttribute("href") ?? "", "http://x").searchParams.get("step"),
        ),
    ).toEqual(["change", "questionnaire", "treatment"]);
    expect(steps.querySelector("[aria-current='step']")?.textContent).toContain("Impact preview");

    // The job ends: the row holds its preview, and the step — still the current one — states the
    // catch-up instead of "current". No second run is asked for.
    world.previewEnds = "SUCCEEDED";
    await waitFor(() => expect(stepNames()[3]).toBe("Step 4 of 5, Impact preview, Catch-up 0.00"), {
      timeout: 10_000,
    });
    expect(
      screen
        .getByRole("navigation", { name: "Modification steps" })
        .querySelector("[aria-current='step']")?.textContent,
    ).toContain("Impact preview");
    expect(stepNames()[4]).toBe("Step 5 of 5, Submit, not started");
    expect(world.sent("POST", "/preview")).toHaveLength(1);
  });

  // 04 §16.14 rev 1.188 (item MOD-PATCH-CLEAR-1): `PATCH` clears a nullable member that is sent as
  // null. Until then no save could remove the amount, and the kind of such a draft was fixed.
  it("a stored price change can change its kind, and the save clears its amount", async () => {
    serveWorkbench();
    const world = serveModification(
      modificationRow({
        kind: "PRICE_CHANGE",
        price_change_amount: "12000.00",
        lines: [
          {
            action: "CHANGE",
            obligation_key: "O1",
            quantity_delta: "0",
            consideration_delta: { amount: "12000.00", currency: "USD" },
          },
        ],
      }),
    );
    openStep("change");

    const amount = await screen.findByRole<HTMLInputElement>("textbox", {
      name: /^Price change amount/,
    });
    expect(amount.value).toBe("12,000.00");
    expect(screen.getByRole("combobox", { name: /^Kind/ }).textContent).toContain("Price change");
    expect(screen.getByRole("combobox", { name: /^Obligation/ }).textContent).toContain("O1");

    // Another kind keeps the stored line and holds no price change amount.
    select("Kind", "Other");
    await screen.findByTestId("SF-07-grid-lines");
    expect(screen.queryByRole("textbox", { name: /^Price change amount/ })).toBeNull();
    fireEvent.click(next());

    await waitFor(() => expect(world.sent("PATCH", MODIFICATION_ID)).toHaveLength(1));
    expect(world.sent("PATCH", MODIFICATION_ID)[0]?.body).toMatchObject({
      kind: "OTHER",
      // No scope description was entered: it goes as null too, not as "".
      rationale: null,
      price_change_amount: null,
    });
    expect(world.row.kind).toBe("OTHER");
    expect(world.row.price_change_amount).toBeNull();
  });

  it("step Treatment takes the override record off the row once every choice is the proposal again", async () => {
    serveWorkbench();
    const world = serveModification(
      classifiedRow({
        chosen_treatments: { O1: "CUMULATIVE_CATCH_UP", O2: "PROSPECTIVE" },
        judgement_record_id: JUDGEMENT_ID,
      }),
      [judgementRecord({ status: "REVIEWED" })],
    );
    openStep("treatment");

    const chosen = await screen.findByRole<HTMLSelectElement>("combobox", {
      name: "Chosen treatment for O1",
    });
    expect(chosen.value).toBe("CUMULATIVE_CATCH_UP");
    expect(await screen.findByTestId("SF-07-banner-override")).toBeTruthy();

    // Back to the proposal: nothing departs, so the record explains nothing.
    fireEvent.change(chosen, { target: { value: "PROSPECTIVE" } });
    await waitFor(() => expect(screen.queryByTestId("SF-07-banner-override")).toBeNull());
    fireEvent.click(next());
    await waitFor(() => expect(world.sent("PATCH", MODIFICATION_ID)).toHaveLength(1));
    expect(world.sent("PATCH", MODIFICATION_ID)[0]?.body).toEqual({
      chosen_treatments: { O1: "PROSPECTIVE", O2: "PROSPECTIVE" },
      ssp_basis: {},
      judgement_record_id: null,
    });
    expect(world.row.judgement_record_id).toBeNull();
  });

  it("a classification that did not answer is offered again", async () => {
    serveWorkbench();
    const world = serveModification(modificationRow());
    world.refuse.classify = () =>
      problemResponse("validation-failed", 422, "The request is not valid", {
        errors: [
          {
            field: "lines[0]",
            rule_id: "S06-R-19",
            message: "Line O2 does not have the shape of a co-term line.",
          },
        ],
      });
    openStep("questionnaire");

    expect(
      await screen.findByText("Line O2 does not have the shape of a co-term line."),
    ).toBeTruthy();
    expect(screen.getByTestId("SF-07-blocked").textContent).toBe(
      "Confirm every answer to continue.",
    );
    // The refusal is not asked for a second time on its own.
    expect(world.sent("POST", "/classify")).toHaveLength(1);

    world.refuse.classify = null;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(
      await screen.findByRole("radiogroup", { name: "Is the added price at SSP?" }),
    ).toBeTruthy();
    expect(world.sent("POST", "/classify")).toHaveLength(2);
    expect(screen.queryByText("Line O2 does not have the shape of a co-term line.")).toBeNull();
  });

  it("the preview step shows the figures of the stored preview and a failed run", async () => {
    serveWorkbench();
    const world = serveModification(classifiedRow());
    world.previewEnds = "FAILED";
    openStep("preview");

    // SCR-ST-12: the failed job, with a way to run it again.
    expect(
      await screen.findByText("The preview could not be calculated. Nothing was changed."),
    ).toBeTruthy();
    expect(screen.getByText("The computation failed")).toBeTruthy();
    expect(screen.getByTestId("SF-07-blocked").textContent).toBe(
      "The preview has to finish before the next step.",
    );
    expect(next().getAttribute("aria-disabled")).toBe("true");

    world.previewEnds = "SUCCEEDED";
    fireEvent.click(screen.getByRole("button", { name: "Run preview" }));
    const allocation = await screen.findByRole("table", { name: "Allocation by obligation" });
    expect(world.sent("POST", "/preview")).toHaveLength(2);
    // Every figure is the API's: no "Change" column on the allocation (ruling R-93 (c)).
    expect(
      within(allocation)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual(["Obligation", "Treatment", "Remaining before", "Remaining after", "Catch-up"]);
    const added = within(allocation).getByRole("rowheader", { name: "O2 (added)" }).closest("tr");
    expect(added?.textContent).toContain("66,726.53");
    const revenue = screen.getByRole("table", { name: "Revenue by period" });
    expect(cellTexts(within(revenue).getAllByRole("row")[1])).toEqual([
      "Sep 2026",
      "9,863.01",
      "11,769.80",
      "+1,906.79",
    ]);
    expect(screen.getByRole("table", { name: "Journal preview" })).toBeTruthy();
    await waitFor(() => expect(screen.queryByTestId("SF-07-blocked")).toBeNull());
    expect(next().getAttribute("aria-disabled")).toBeNull();
  });

  const COMPUTED =
    "Computed 16 Sep 2026 09:40 UTC for Sep 2026: the entries the approval would post then — the change's effect with the period's amounts not posted yet.";
  const MOVED =
    "Sep 2026 is no longer the latest open period. The entries at approval will differ from these.";
  it("the journal preview says when and for which period it was computed", async () => {
    serveWorkbench();
    serveModification(previewedRow());
    openStep("preview");

    // 04 API-S-ImpactSummary (rev 1.210): the entries the approval would post, each account with
    // both of its sides.
    const journal = await screen.findByRole("table", { name: "Journal preview" });
    expect(
      within(journal)
        .getAllByRole("row")
        .slice(1)
        .map((row) => cellTexts(row)),
    ).toEqual([
      ["2100 · Contract liability", "Contract liability", "2,120.55", "213.76"],
      ["4010 · Revenue - services and subscriptions", "Revenue", "213.76", "2,120.55"],
    ]);
    // The period reads by its name once the calendar of the entity is read.
    await waitFor(() =>
      expect(screen.getByTestId("SF-07-journal-computed").textContent).toBe(COMPUTED),
    );
    // September is still the latest postable period: nothing more is said.
    expect(screen.queryByTestId("SF-07-banner-period-moved")).toBeNull();
  });

  it("the journal preview warns once its period is no longer the latest open one, and Run preview computes it again", async () => {
    serveWorkbench();
    const world = serveModification(previewedRow());
    serveOctoberOpen();
    openStep("preview");

    const warning = await screen.findByTestId("SF-07-banner-period-moved");
    expect(within(warning).getByText(MOVED)).toBeTruthy();
    expect(warning.querySelector("[data-tone]")?.getAttribute("data-tone")).toBe("warning");
    expect(screen.getByTestId("SF-07-journal-computed").textContent).toBe(COMPUTED);
    // The stored preview is not stale: the step is not held and nothing ran by itself.
    expect(screen.queryByTestId("SF-07-blocked")).toBeNull();
    expect(world.sent("POST", "/preview")).toHaveLength(0);

    // The run computes the entries for October and stores them in place of September's.
    world.postablePeriod = "FY2026-P10";
    fireEvent.click(within(warning).getByRole("button", { name: "Run preview" }));
    await waitFor(() => expect(world.sent("POST", "/preview")).toHaveLength(1));
    await waitFor(() => expect(screen.queryByTestId("SF-07-banner-period-moved")).toBeNull());
    expect(screen.getByTestId("SF-07-journal-computed").textContent).toBe(
      COMPUTED.replace("for Sep 2026", "for Oct 2026"),
    );
  });

  it("a preview stored before the API stated its instant and period shows neither line", async () => {
    serveWorkbench();
    const stored = previewedRow();
    serveModification({
      ...stored,
      impact_preview:
        stored.impact_preview === null
          ? null
          : { ...stored.impact_preview, computed_at: null, computed_period_key: null },
    });
    serveOctoberOpen();
    openStep("preview");

    await screen.findByRole("table", { name: "Journal preview" });
    expect(screen.queryByTestId("SF-07-journal-computed")).toBeNull();
    expect(screen.queryByTestId("SF-07-banner-period-moved")).toBeNull();
  });

  it("a classified draft read with the proposals of its classification is not classified again", async () => {
    serveWorkbench();
    // 04 T-CON-06 `classification` (rev 1.210, item MOD-PREFILL-READ-1): every answer of the row
    // carries `prefill_reasons`, so a read holds the proposals of a question that is not answered.
    const world = serveModification(
      classifiedRow({
        questionnaire: { O2: CONFIRMED_O2 },
        proposal_detail: { "class[O1]": "D", "class[O2]": "D", "ssp_version[O2]": "US-LIST@v1" },
        prefill_reasons: {
          O1: {
            remaining_goods_distinct_from_transferred: {
              value: true,
              reason_key: "modifications.prefill.remaining_goods_distinct_from_transferred.series",
              params: { progress: "0.354794520547945205", progress_measure: "TIME_ELAPSED" },
            },
          },
        },
      }),
    );
    openStep("questionnaire");

    expect(
      answerOf(
        await screen.findByRole("radiogroup", {
          name: /^Are the remaining goods or services distinct from those already transferred\?/,
        }),
      ),
    ).toBe("Yes");
    expect(screen.getAllByText("Prefilled")).toHaveLength(1);
    expect(confirmBox("O2").checked).toBe(true);
    expect(confirmBox("O1").checked).toBe(false);
    expect(world.sent("POST", "/classify")).toHaveLength(0);
  });

  it("a classified draft whose classification proposes nothing is not classified again", async () => {
    serveWorkbench();
    // 04 §16.14 rev 1.286 (item MOD-CLASSIFICATION-KEYS-1): `prefill_reasons` holds the
    // obligations alone, so it is `{}` where the engine proposes no answer — here for O1, whose
    // question is open and which the engine found satisfied — and the row states its
    // classification by `proposal_detail`. Before, the detail was the member `proposal` of
    // `prefill_reasons`, and a row without it was taken for one whose proposals are unknown.
    const world = serveModification(
      classifiedRow({
        questionnaire: { O2: CONFIRMED_O2 },
        prefill_reasons: {},
        proposal_detail: { "class[O1]": "S", "class[O2]": "D", "ssp_version[O2]": "US-LIST@v1" },
      }),
    );
    openStep("questionnaire");

    await screen.findByRole("radiogroup", { name: /^Is the added price at SSP\?/ });
    expect(confirmBox("O2").checked).toBe(true);
    expect(screen.queryByText("Prefilled")).toBeNull();
    expect(world.sent("POST", "/classify")).toHaveLength(0);
  });

  it("the footer says More below while the step continues beneath it", async () => {
    serveWorkbench();
    serveModification(previewedRow());
    openStep("preview");

    await screen.findByRole("region", { name: "Impact summary (USD)" });
    expect(screen.queryByRole("button", { name: "More below" })).toBeNull();
    // jsdom has no layout: the shell's scrolling region is given 700 px that hold 1,600 px.
    const region = screen.getByRole("main");
    Object.defineProperty(region, "scrollHeight", { configurable: true, value: 1600 });
    Object.defineProperty(region, "clientHeight", { configurable: true, value: 700 });
    Object.defineProperty(region, "scrollTop", { configurable: true, writable: true, value: 0 });
    fireEvent.scroll(region);

    // DESIGN_SYSTEM rev 1.9 (DS-CMP-18 footer): the cue is the first row of the wizard's footer.
    const more = await screen.findByRole("button", { name: "More below" });
    expect(more.getAttribute("data-testid")).toBe("SF-07-more-below");
    expect(more.compareDocumentPosition(next()) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0);
  });

  it("Submit for approval waits for the review of the override record and shows a refusal", async () => {
    serveWorkbench();
    const linked = judgementRecord({ status: "SUBMITTED" });
    const world = serveModification(
      previewedRow({
        chosen_treatments: { O1: "CUMULATIVE_CATCH_UP", O2: "PROSPECTIVE" },
        judgement_record_id: JUDGEMENT_ID,
      }),
      [linked],
    );
    const { queryClient } = openStep("submit");

    const summary = await screen.findByTestId("SF-07-summary");
    expect(Array.from(summary.querySelectorAll("dt"), (term) => term.textContent)).toEqual([
      "Kind",
      "Reference",
      "Effective date",
      "Treatments",
      "Linked estimate versions",
      "Linked judgement records",
      "Flags",
    ]);
    expect(within(summary).getByText("No estimate version is linked.")).toBeTruthy();
    expect(within(summary).getByText("Treatment override")).toBeTruthy();
    const submit = () => screen.getByRole("button", { name: "Submit for approval" });
    // The record is submitted, not reviewed: the API would refuse (REQ-MOD-002).
    expect((await screen.findByTestId("SF-07-blocked")).textContent).toBe(
      "Judgement record JDG-000012 waits for review. The modification can be submitted once it is reviewed.",
    );
    expect(submit().getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(submit());
    expect(world.sent("POST", "/submit")).toHaveLength(0);

    // Reviewed: the command is open; the API's refusal is shown as it comes.
    world.judgements = [judgementRecord({ status: "REVIEWED" })];
    await queryClient.invalidateQueries({ queryKey: ["modification-judgements"] });
    await waitFor(() => expect(screen.queryByTestId("SF-07-blocked")).toBeNull());
    world.refuse.submit = overrideRefusal;
    type(/^Comment/, "  Seats added by change order 7.  ");
    fireEvent.click(submit());
    expect(
      await screen.findByText(
        "The chosen treatment of O1 differs from the proposal; link a reviewed judgement record of topic MODIFICATION_TREATMENT_OVERRIDE.",
      ),
    ).toBeTruthy();
    expect(world.sent("POST", "/submit")[0]?.body).toEqual({
      comment: "Seats added by change order 7.",
    });
    expect(world.row.status).toBe("DRAFT");

    // Accepted: a submission routes one request (PRD rev 1.158 J-06.5), the toast names it, and the
    // screen is the read-only detail.
    world.refuse.submit = null;
    const reads = world.rowReads;
    fireEvent.click(submit());
    expect(
      await screen.findByText(
        "Submitted for approval. Request APR-000434 is waiting for approval.",
      ),
    ).toBeTruthy();
    expect(await screen.findByTestId("SF-07-detail-page")).toBeTruthy();
    expect(await screen.findByRole("list", { name: "Approval routing" })).toBeTruthy();
    // `/submit` answers the row as `GET` does, with its stored preview (04 §16.14 rev 1.188, item
    // MOD-ANSWER-PREVIEW-1): the snapshot is the answer's, and the row is not read a second time.
    expect(await screen.findByText("Snapshot e9ac7d5ea7aa reviewed by the approver.")).toBeTruthy();
    expect(world.rowReads).toBe(reads);
  });

  // SCREENS §7.3 (rev 1.26; PRD SM-03 "Discard draft"; item MOD-DISCARD-1).
  it("Discard draft voids the draft after a confirmation and opens the Modifications tab", async () => {
    serveWorkbench();
    const world = serveModification(previewedRow());
    const { router, queryClient } = openStep("submit");

    await screen.findByTestId("SF-07-summary");
    fireEvent.click(screen.getByRole("button", { name: "Discard draft" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Discard this draft modification?",
    });
    expect(
      within(dialog).getByText("The draft is voided and can no longer be edited or submitted."),
    ).toBeTruthy();
    // Nothing is sent before the confirmation; "Cancel" leaves the draft.
    expect(world.sent("POST", "/discard")).toHaveLength(0);
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(world.row.status).toBe("DRAFT");

    fireEvent.click(screen.getByRole("button", { name: "Discard draft" }));
    fireEvent.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Discard draft" }),
    );
    await waitFor(() => expect(world.sent("POST", "/discard")).toHaveLength(1));
    // The command takes no body: the screen asks for a confirmation, not a reason.
    expect(world.sent("POST", "/discard")[0]?.body).toBeNull();
    expect(await screen.findByText("The draft modification was discarded.")).toBeTruthy();
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(`/contracts/${CONTRACT_ID}/modifications`),
    );
    expect(router.state.location.search).toBe(`?${CONTEXT}`);
    // The row the command answered replaces the draft that was read, without another read.
    await waitFor(() =>
      expect(queryClient.getQueryData<Modification>(modificationKey(MODIFICATION_ID))?.status).toBe(
        "VOIDED",
      ),
    );
  });

  it("a refused discard names the judgement record whose review is pending, and the draft stays", async () => {
    serveWorkbench();
    const world = serveModification(
      previewedRow({
        chosen_treatments: { O1: "CUMULATIVE_CATCH_UP", O2: "PROSPECTIVE" },
        judgement_record_id: JUDGEMENT_ID,
      }),
      [judgementRecord({ status: "SUBMITTED" })],
    );
    // PRD ERR-82: `invalid-transition` under the rule id of SM-03, one entry per record.
    world.refuse.discard = () =>
      problemResponse("invalid-transition", 409, "Action not available in this state", {
        errors: [
          {
            field: null,
            rule_id: "SM-03",
            message:
              "Judgement record JDG-000012 of this modification is waiting for review. Its preparer withdraws the review request first.",
          },
        ],
      });
    const { router } = openStep("submit");

    await screen.findByTestId("SF-07-summary");
    fireEvent.click(screen.getByRole("button", { name: "Discard draft" }));
    const dialog = await screen.findByRole("alertdialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Discard draft" }));
    expect(
      await within(dialog).findByText(
        "Judgement record JDG-000012 of this modification is waiting for review. Its preparer withdraws the review request first.",
      ),
    ).toBeTruthy();
    expect(within(dialog).getByText("Action not available in this state")).toBeTruthy();
    expect(world.row.status).toBe("DRAFT");
    expect(router.state.location.search).toContain("step=submit");
    expect(screen.queryByText("The draft modification was discarded.")).toBeNull();
  });

  // SCREENS §0.6 SCR-PERM-02 (a): a modification is a record of the contract's legal entity.
  it("Discard draft is offered where modification.create is held for the contract's entity", async () => {
    const scoped = (entityId: string) =>
      signedInMe({
        permissions: ["contract.read", "config.read", "ssp.read", "modification.create"],
        permission_scopes: {
          "contract.read": "*",
          "config.read": "*",
          "ssp.read": "*",
          "modification.create": [entityId],
        },
      });
    serveWorkbench();
    serveModification(previewedRow());
    openStep("submit", scoped("0a1b2c3d-4e5f-4a6b-8c7d-0000000000ff"));
    await screen.findByTestId("SF-07-summary");
    expect(screen.queryByRole("button", { name: "Discard draft" })).toBeNull();
    cleanup();

    serveWorkbench();
    serveModification(previewedRow());
    openStep("submit", scoped(AVM_US.id));
    await screen.findByTestId("SF-07-summary");
    expect(screen.getByRole("button", { name: "Discard draft" })).toBeTruthy();
  });

  it("a session without judgement.create is told what to ask for", async () => {
    serveWorkbench();
    serveModification(classifiedRow({ chosen_treatments: { O1: "MIXED", O2: "PROSPECTIVE" } }));
    openStep(
      "treatment",
      signedInMe({ permissions: ["contract.read", "config.read", "modification.create"] }),
    );

    const banner = await screen.findByTestId("SF-07-banner-override");
    expect(within(banner).getByText(OVERRIDE)).toBeTruthy();
    expect(within(banner).queryByRole("button", { name: "Record judgement" })).toBeNull();
    expect(
      within(banner).getByText(
        "Ask a workspace administrator for a role that includes preparing judgement records.",
      ),
    ).toBeTruthy();
    expect(next().getAttribute("aria-disabled")).toBe("true");
  });
});

describe("SF-07 a new modification", () => {
  function serveNew(contract?: Record<string, unknown>) {
    serveWorkbench(contract === undefined ? {} : { contract });
    return serveModification(modificationRow());
  }

  it("a subscription action creates an ordinary modification of its kind and opens the questionnaire", async () => {
    const world = serveNew();
    const { router } = open(
      `/contracts/${CONTRACT_ID}/modifications/new?${CONTEXT}&action=co_term`,
    );

    expect(await screen.findByRole("heading", { level: 1, name: "New modification" })).toBeTruthy();
    // The contract has one obligation: it is chosen, and the added obligation takes the next key.
    const key = await screen.findByRole<HTMLInputElement>("textbox", {
      name: /^New obligation key/,
    });
    expect(key.value).toBe("O2");
    expect(screen.getByText("Co-term")).toBeTruthy();
    expect(screen.getByText("Ends on 31 Dec 2027")).toBeTruthy();
    expect(stepNames()[0]).toBe("Step 1 of 5, Change, current");

    // What is missing is named on its field; nothing is sent.
    fireEvent.click(next());
    expect(await screen.findAllByText("Enter a reference for this modification.")).not.toHaveLength(
      0,
    );
    expect(screen.getAllByText("Enter the quantity this change adds.")).not.toHaveLength(0);
    expect(world.sent("POST", "/modifications")).toHaveLength(0);

    type(/^Quantity/, "50");
    type(/^Price/, "60,000.00");
    type(/^Effective date/, "16 Sep 2026");
    type(/^Reference/, REFERENCE);
    fireEvent.click(next());

    await waitFor(() => expect(world.sent("POST", "/modifications")).toHaveLength(1));
    // The S06-R-19 shape of a co-term line: added from the effective date to the end of the term.
    expect(world.sent("POST", "/modifications")[0]?.body).toEqual({
      kind: "CO_TERM",
      reference: REFERENCE,
      effective_date: "2026-09-16",
      lines: [
        {
          action: "ADD",
          obligation_key: "O2",
          product_code: "AVM-SEAT-MO",
          quantity_delta: "50",
          consideration_delta: { amount: "60000.00", currency: "USD" },
          start_date: "2026-09-16",
          end_date: "2027-12-31",
        },
      ],
    });
    // SCREENS §7.3: the draft exists; the URL is SF-07:detail at the next step, without `action`.
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(
        `/contracts/${CONTRACT_ID}/modifications/${MODIFICATION_ID}`,
      ),
    );
    expect(router.state.location.search).toBe(`?${CONTEXT}&step=questionnaire`);
    expect(
      await screen.findByRole("radiogroup", { name: "Is the added price at SSP?" }),
    ).toBeTruthy();
  });

  it("the general form names what is missing and posts a price change with a zero quantity", async () => {
    const world = serveNew();
    open(
      `/contracts/${CONTRACT_ID}/modifications/new?${CONTEXT}&kind=PRICE_CHANGE&obligation=${O1_ID}`,
    );

    // SCR-URL-31: the kind and the obligation of the link are preselected and stay editable.
    const kind = await screen.findByRole("combobox", { name: /^Kind/ });
    expect(kind.textContent).toContain("Price change");
    expect(screen.getByRole("combobox", { name: /^Obligation/ }).textContent).toContain("O1");
    expect(screen.queryByTestId("SF-07-grid-lines")).toBeNull();

    fireEvent.click(next());
    expect(
      await screen.findAllByText("Enter a price change amount other than zero."),
    ).not.toHaveLength(0);
    expect(screen.getAllByText("Enter the effective date.")).not.toHaveLength(0);

    type(/^Price change amount/, "12,000.00");
    type(/^Reference/, "CR-MARROWBY-2026-10");
    type(/^Effective date/, "01 Oct 2026");
    fireEvent.click(next());
    await waitFor(() => expect(world.sent("POST", "/modifications")).toHaveLength(1));
    expect(world.sent("POST", "/modifications")[0]?.body).toEqual({
      kind: "PRICE_CHANGE",
      reference: "CR-MARROWBY-2026-10",
      effective_date: "2026-10-01",
      rationale: null,
      lines: [
        {
          action: "CHANGE",
          obligation_key: "O1",
          quantity_delta: "0",
          consideration_delta: { amount: "12000.00", currency: "USD" },
        },
      ],
      price_change_amount: "12000.00",
    });
  });

  it("a general modification needs a line or a price change, and a backdated one says what replays", async () => {
    const world = serveNew();
    open(`/contracts/${CONTRACT_ID}/modifications/new?${CONTEXT}`);

    await screen.findByTestId("SF-07-grid-lines");
    select("Kind", "Add obligation");
    type(/^Reference/, "CR-MARROWBY-2026-11");
    // BR-MOD-04: before the latest event of the contract (20 Sep 2026); allowed, with the note.
    type(/^Effective date/, "16 Sep 2026");
    expect(
      await screen.findByText(
        "Effective 16 Sep 2026 is before the latest event on this contract (20 Sep 2026). Events from 16 Sep 2026 replay in order.",
      ),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Remove line 1" }));
    fireEvent.click(next());
    expect(await screen.findAllByText("Add at least one line or a price change.")).not.toHaveLength(
      0,
    );
    expect(world.sent("POST", "/modifications")).toHaveLength(0);
  });

  it("a contract that is not active offers no form", async () => {
    serveNew(workbenchContract({ status: "COMPLETED" }));
    const { router } = open(`/contracts/${CONTRACT_ID}/modifications/new?${CONTEXT}`);

    expect(
      await screen.findByRole("heading", { name: "Modifications apply to active contracts" }),
    ).toBeTruthy();
    expect(screen.getByText(`${K02} is Completed.`)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Next" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Back to the contract" }));
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(`/contracts/${CONTRACT_ID}/modifications`),
    );
  });

  it("without modification.create the screen names the permission", async () => {
    serveNew();
    open(
      `/contracts/${CONTRACT_ID}/modifications/new?${CONTEXT}`,
      signedInMe({ permissions: ["contract.read"] }),
    );

    // SCR-PERM-01.
    expect(
      await screen.findByRole("heading", { name: "You do not have access to modifications" }),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Ask a workspace administrator for a role that includes preparing modifications.",
      ),
    ).toBeTruthy();
  });
});

// SCREENS §7.4 "Linked items panel", §7.8 (rev 1.33; 04 §16.14 rev 1.210 `linked_estimate_versions`,
// T-CON-13 `modification_id`; PRD BR-MOD-02, ERR-83, ERR-87).
describe("SF-07 the linked estimate versions of a draft", () => {
  // The linked estimate versions are prepared with `estimate.create` (SCREENS §7.1).
  const PREPARER = signedInMe({
    permissions: [
      "contract.read",
      "config.read",
      "ssp.read",
      "modification.create",
      "judgement.create",
      "estimate.create",
    ],
  });

  /** The `EAC` element's version 1, approved. */
  function eacApproved() {
    return versionRow({
      version_no: 1,
      status: "APPROVED",
      effective_date: "2026-02-01",
      expected_total_amount: "700000.00",
      costs_incurred_to_date: money("420000.00"),
      progress_ratio: "0.6",
      rationale: "Bid estimate at contract inception.",
    });
  }

  /** Version 2 of `EAC`, created inside the modification of this world. */
  function eacLinked(overrides: Partial<ReturnType<typeof versionRow>> = {}) {
    return versionRow({
      version_no: 2,
      status: "DRAFT",
      effective_date: "2026-09-10",
      expected_total_amount: "820000.00",
      costs_incurred_to_date: money("420000.00"),
      progress_ratio: "0.512195",
      rationale: "Change order CO-07 adds 120,000.00 of cost",
      modification_id: MODIFICATION_ID,
      ...overrides,
    });
  }

  function fill(element: HTMLElement, value: string) {
    fireEvent.change(element, { target: { value } });
    fireEvent.blur(element);
  }

  it("step Change lists the estimate versions created inside the draft with their figures", async () => {
    serveWorkbench();
    const estimates = serveEstimates([estimateRow()], { [EAC_ID]: [eacLinked(), eacApproved()] });
    const world = serveModification(modificationRow());
    world.estimates = estimates;
    openStep("change");

    const table = await screen.findByRole("table", { name: "Linked estimate versions" });
    expect(table.getAttribute("data-testid")).toBe("SF-07-grid-estimate-versions");
    expect(Array.from(table.querySelectorAll("thead th"), (cell) => cell.textContent)).toEqual([
      "Element",
      "Kind",
      "Version",
      "Figure",
      "Status",
    ]);
    // The figure is the key figure of the kind, read from the version itself.
    await waitFor(() =>
      expect(cellTexts(within(table).getAllByRole("row")[1])).toEqual([
        "EAC",
        "Estimated total costs",
        "2",
        "820,000.00",
        "Draft",
      ]),
    );
    // The element's cell opens SF-03:estimate, where a version is edited, submitted and discarded.
    expect(within(table).getByRole("link", { name: "EAC" }).getAttribute("href")).toBe(
      `/contracts/${CONTRACT_ID}/estimates/${EAC_ID}?${CONTEXT}`,
    );
    // Without `estimate.create` the versions are read and none is added from here.
    expect(screen.queryByRole("button", { name: "Add estimate version" })).toBeNull();
  });

  it("Add estimate version opens the element's version drawer, sends modification_id and lists the version", async () => {
    serveWorkbench();
    const estimates = serveEstimates([estimateRow()], { [EAC_ID]: [eacApproved()] });
    const world = serveModification(modificationRow());
    world.estimates = estimates;
    openStep("change", PREPARER);

    expect(
      await screen.findByRole("heading", { level: 3, name: "Linked estimate versions" }),
    ).toBeTruthy();
    expect(screen.getByText("No estimate version is linked.")).toBeTruthy();
    const add = await screen.findByRole("button", { name: "Add estimate version" });
    await waitFor(() => expect(add.getAttribute("aria-busy")).toBeNull());
    fireEvent.click(add);

    // One element: its drawer opens, with the figures of the approved version (SCREENS §8.4).
    const drawer = await screen.findByRole("dialog", { name: "New estimate version · EAC" });
    const total = within(drawer).getByLabelText<HTMLInputElement>("Estimated total costs (USD)");
    expect(total.value).toBe("700,000.00");
    fill(within(drawer).getByLabelText("Effective date"), "10 Sep 2026");
    fill(total, "820,000.00");
    fill(within(drawer).getByLabelText("Rationale"), "Change order CO-07 adds 120,000.00 of cost");
    fireEvent.click(within(drawer).getByRole("button", { name: "Save draft" }));

    // 04 T-CON-13: the version names the draft modification from its creation on.
    await waitFor(() => expect(estimates.sent("POST", "/versions")).toHaveLength(1));
    expect(estimates.sent("POST", "/versions")[0]?.body).toMatchObject({
      modification_id: MODIFICATION_ID,
      effective_date: "2026-09-10",
      expected_total_amount: "820000.00",
      rationale: "Change order CO-07 adds 120,000.00 of cost",
    });
    // The row is read again and lists the version.
    const table = await screen.findByRole("table", { name: "Linked estimate versions" });
    await waitFor(() =>
      expect(cellTexts(within(table).getAllByRole("row")[1])).toEqual([
        "EAC",
        "Estimated total costs",
        "2",
        "820,000.00",
        "Draft",
      ]),
    );
    expect(screen.queryByText("No estimate version is linked.")).toBeNull();
    // The one element holds a draft now: the command is unavailable and says so in a visible line.
    await waitFor(() =>
      expect(screen.getByTestId("SF-07-linked-blocked").textContent).toBe(
        "Version 2 is a draft. Submit or discard it first.",
      ),
    );
    expect(
      screen.getByRole("button", { name: "Add estimate version" }).getAttribute("aria-disabled"),
    ).toBe("true");
  });

  it("with several elements Add estimate version offers each, and one with an open version says why", async () => {
    serveWorkbench();
    const rebate = estimateRow({
      id: REBATE_ID,
      estimate_kind: "VARIABLE_CONSIDERATION",
      element_code: "REBATE-DR-01",
      vc_element_type: "REBATE",
      direction: "DECREASE",
      method: "MOST_LIKELY_AMOUNT",
    });
    const estimates = serveEstimates([estimateRow(), rebate], {
      [EAC_ID]: [eacApproved()],
      [REBATE_ID]: [
        versionRow({ estimate_id: REBATE_ID, version_no: 2, status: "DRAFT" }),
        versionRow({ estimate_id: REBATE_ID, version_no: 1, status: "APPROVED" }),
      ],
    });
    const world = serveModification(modificationRow());
    world.estimates = estimates;
    openStep("change", PREPARER);

    // Several elements: the command is a menu of them, once they are read.
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Add estimate version" }).getAttribute("aria-haspopup"),
      ).toBe("menu"),
    );
    fireEvent.click(screen.getByRole("button", { name: "Add estimate version" }));
    const items = await screen.findAllByRole("menuitem");
    expect(items.map((item) => item.textContent)).toEqual([
      "EAC · Estimated total costs",
      "REBATE-DR-01 · Variable consideration",
    ]);
    // A new version starts while no version of the element is a draft or waits for approval.
    expect(items[1]?.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(items[0] as HTMLElement);
    expect(await screen.findByRole("dialog", { name: "New estimate version · EAC" })).toBeTruthy();
  });

  it("a contract without an estimated element says where to add one", async () => {
    serveWorkbench();
    const estimates = serveEstimates();
    const world = serveModification(modificationRow());
    world.estimates = estimates;
    openStep("change", PREPARER);

    const add = () => screen.getByRole("button", { name: "Add estimate version" });
    await screen.findByRole("button", { name: "Add estimate version" });
    await waitFor(() => expect(add().getAttribute("aria-disabled")).toBe("true"));
    // SCREENS §0.6 SCR-PERM-03: the reason is a visible line; the tooltip repeats it and is no
    // reader's only copy (DESIGN_SYSTEM DS-CMP-27).
    const reason = screen.getByTestId("SF-07-linked-blocked");
    expect(reason.textContent).toBe("Add an estimated element on the Estimates tab first.");
    expect(reason.closest("[hidden]")).toBeNull();
    expect(reason.getAttribute("role")).toBeNull();
    expect(
      screen.getAllByText("Add an estimated element on the Estimates tab first."),
    ).toHaveLength(2);
    fireEvent.click(add());
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  const NOT_APPROVED =
    "Estimate version EAC v2 of this modification is not approved. It is approved before the modification is submitted.";

  it("the summary lists the linked versions, and Submit for approval waits until each is approved", async () => {
    serveWorkbench();
    const estimates = serveEstimates([estimateRow()], { [EAC_ID]: [eacLinked(), eacApproved()] });
    const world = serveModification(previewedRow());
    world.estimates = estimates;
    const { queryClient } = openStep("submit");

    const summary = await screen.findByTestId("SF-07-summary");
    const versions = within(summary).getByText("Linked estimate versions").nextElementSibling;
    expect(versions?.textContent).toContain("EAC v2");
    expect(versions?.textContent).toContain("Draft");

    // PRD ERR-87, said before the press: the versions are approved before the submission.
    const submit = () => screen.getByRole("button", { name: "Submit for approval" });
    expect((await screen.findByTestId("SF-07-blocked")).textContent).toBe(NOT_APPROVED);
    expect(submit().getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(submit());
    expect(world.sent("POST", "/submit")).toHaveLength(0);

    // Approved on its own request: the command is open and the submission goes out.
    estimates.versions.set(EAC_ID, [
      eacLinked({ status: "APPROVED" }),
      { ...eacApproved(), status: "SUPERSEDED" },
    ]);
    await queryClient.invalidateQueries({ queryKey: ["modification"] });
    await waitFor(() => expect(screen.queryByTestId("SF-07-blocked")).toBeNull());
    expect(versions?.textContent).toContain("Approved");
    fireEvent.click(submit());
    await waitFor(() => expect(world.sent("POST", "/submit")).toHaveLength(1));
    await waitFor(() => expect(world.row.status).toBe("SUBMITTED"));
  });

  it("a discarded linked version does not hold the submission, and the API's refusal is shown as it comes", async () => {
    serveWorkbench();
    const estimates = serveEstimates([estimateRow()], {
      [EAC_ID]: [eacLinked({ status: "VOIDED" }), eacApproved()],
    });
    const world = serveModification(previewedRow());
    world.estimates = estimates;
    openStep("submit");

    const summary = await screen.findByTestId("SF-07-summary");
    expect(
      within(summary).getByText("Linked estimate versions").nextElementSibling?.textContent,
    ).toContain("Void");
    expect(screen.queryByTestId("SF-07-blocked")).toBeNull();
    // The backstop: a version another session returned to draft since this row was read.
    world.refuse.submit = () =>
      problemResponse("invalid-transition", 409, "Action not available in this state", {
        errors: [{ field: null, rule_id: "SM-03", message: NOT_APPROVED }],
      });
    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));
    expect(await screen.findByText(NOT_APPROVED)).toBeTruthy();
    expect(world.row.status).toBe("DRAFT");
  });

  it("a discard while a linked version waits for approval shows the API's sentence, and the draft stays", async () => {
    serveWorkbench();
    const estimates = serveEstimates([estimateRow()], {
      [EAC_ID]: [eacLinked({ status: "SUBMITTED" }), eacApproved()],
    });
    const world = serveModification(modificationRow());
    world.estimates = estimates;
    openStep("change");

    fireEvent.click(await screen.findByRole("button", { name: "Discard draft" }));
    const dialog = await screen.findByRole("alertdialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Discard draft" }));
    // PRD ERR-83.
    expect(
      await within(dialog).findByText(
        "Estimate version EAC v2 of this modification is waiting for approval. Its preparer withdraws it first.",
      ),
    ).toBeTruthy();
    expect(world.row.status).toBe("DRAFT");
  });

  it("Add estimate version is offered where estimate.create is held for the contract's entity", async () => {
    // SCREENS §0.6 SCR-PERM-02 (a): a command held for another entity only is not rendered.
    const scoped = (entityId: string) =>
      signedInMe({
        permissions: [
          "contract.read",
          "config.read",
          "ssp.read",
          "modification.create",
          "estimate.create",
        ],
        permission_scopes: {
          "contract.read": "*",
          "config.read": "*",
          "ssp.read": "*",
          "modification.create": "*",
          "estimate.create": [entityId],
        },
      });
    serveWorkbench();
    const elsewhere = serveEstimates([estimateRow()], { [EAC_ID]: [eacApproved()] });
    const other = serveModification(modificationRow());
    other.estimates = elsewhere;
    openStep("change", scoped("0a1b2c3d-4e5f-4a6b-8c7d-0000000000ff"));
    expect(
      await screen.findByRole("heading", { level: 3, name: "Linked estimate versions" }),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Add estimate version" })).toBeNull();
    cleanup();

    serveWorkbench();
    const estimates = serveEstimates([estimateRow()], { [EAC_ID]: [eacApproved()] });
    const world = serveModification(modificationRow());
    world.estimates = estimates;
    openStep("change", scoped(AVM_US.id));
    expect(await screen.findByRole("button", { name: "Add estimate version" })).toBeTruthy();
  });

  it("a failed read of the elements, or of an element's versions, says so, and Retry reads it again", async () => {
    serveWorkbench();
    const estimates = serveEstimates([estimateRow()], { [EAC_ID]: [eacApproved()] });
    const world = serveModification(modificationRow());
    world.estimates = estimates;
    // Each read fails while its switch is on; afterwards the world answers it.
    const down = { elements: true, versions: true };
    const failed = () => problemResponse(null, 500, "Internal Server Error");
    server.use(
      http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/estimates`), () =>
        down.elements ? failed() : undefined,
      ),
      http.get(apiUrl(`/api/v1/estimates/${EAC_ID}/versions`), () =>
        down.versions ? failed() : undefined,
      ),
    );
    openStep("change", PREPARER);

    // Without the elements the command is not offered: the panel says what could not be read.
    const heading = await screen.findByRole("heading", {
      level: 3,
      name: "Linked estimate versions",
    });
    const panel = heading.closest("section");
    if (panel === null) {
      throw new Error("the heading of the linked estimate versions stands in no section");
    }
    expect(
      await within(panel).findByRole("heading", { level: 4, name: "Could not load estimates" }),
    ).toBeTruthy();
    expect(within(panel).queryByRole("button", { name: "Add estimate version" })).toBeNull();
    down.elements = false;
    fireEvent.click(within(panel).getByRole("button", { name: "Retry" }));
    await within(panel).findByRole("button", { name: "Add estimate version" });
    await waitFor(() =>
      expect(
        within(panel)
          .getByRole("button", { name: "Add estimate version" })
          .getAttribute("aria-busy"),
      ).toBeNull(),
    );
    expect(within(panel).queryByText("Could not load estimates")).toBeNull();

    // The versions the drawer starts from cannot be read: no drawer opens until Retry reads them.
    fireEvent.click(within(panel).getByRole("button", { name: "Add estimate version" }));
    expect(
      await within(panel).findByRole("heading", { level: 4, name: "Could not load the versions" }),
    ).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
    down.versions = false;
    fireEvent.click(within(panel).getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("dialog", { name: "New estimate version · EAC" })).toBeTruthy();
    expect(within(panel).queryByText("Could not load the versions")).toBeNull();
  });
});

// PRD SM-03 REJECTED → DRAFT, "Revise" (04 §16.14 rev 1.236, item MOD-REJECTED-REVISE-1; SCREENS
// §7.10, rev 1.65): the row of a revised draft names the rejected request until the next submission
// makes a new one. The wizard read that request for the notice of a voided one alone, so a revised
// draft opened later said nothing of where it came from.
describe("SF-07 a draft that revises a rejected modification", () => {
  const REVISED =
    "This draft revises a rejected modification. Request APR-000434 stays closed; submitting makes a new one.";

  function serveRevised() {
    serveWorkbench();
    const world = serveModification(classifiedRow({ approval_request_id: APPROVAL_ID }));
    world.approvalStatus = "REJECTED";
    return world;
  }

  it("a draft that revises a rejected modification names the closed request on every step, with a link where the request screen is built", async () => {
    serveRevised();
    renderApp(`${DETAIL}?${CONTEXT}&step=change`, {
      me: MAYA,
      screenRoutes: [
        ...ROUTES,
        probeRoute("SF-12:request", "/approvals/requests/:requestId", "approvals.title"),
      ],
    });

    const notice = await screen.findByText(REVISED);
    const banner = notice.closest<HTMLElement>("[data-tone]");
    expect(banner?.getAttribute("data-tone")).toBe("info");
    expect(screen.getByRole("link", { name: "View request" }).getAttribute("href")).toBe(
      `/approvals/requests/${APPROVAL_ID}?${CONTEXT}`,
    );
    // The request was decided, not voided: the warning of a voided request is another state.
    expect(
      screen.queryByText(
        "The approval request was voided because this modification changed after submission. Resubmit it.",
      ),
    ).toBeNull();
    // The notice stands above the step, whichever it is.
    await screen.findByRole("textbox", { name: /^Scope description/ });
    fireEvent.click(next());
    await screen.findByRole("radiogroup", { name: /^Is the added price at SSP\?/ });
    expect(screen.getByText(REVISED)).toBeTruthy();
    cleanup();

    // Without the request screen the sentence names the request and offers no link.
    serveRevised();
    openStep("change");
    await screen.findByText(REVISED);
    expect(screen.queryByRole("link", { name: "View request" })).toBeNull();
  });
});

// The judgement records of a draft under E-57 `VOIDED` and PRD ERR-95 (SCREENS §7.4, §7.6 and §7.8,
// rev 1.66; 04 API-R-33 rev 1.242, §16.14 rev 1.242): a record that was discarded read as one that
// waits — its number in the banner and no "Record judgement"; a draft the judgement drawer left
// behind stayed in "Linked judgement records" without a command, and it holds the submission.
describe("SF-07 the judgement records of a draft", () => {
  const OTHER_ID = "7a7a7a7a-7a7a-4a7a-8a7a-7a7a7a7a7a7a";
  const DEPARTING = {
    chosen_treatments: { O1: "CUMULATIVE_CATCH_UP", O2: "PROSPECTIVE" },
    judgement_record_id: JUDGEMENT_ID,
  } as const;
  const ERR_95 = (number: string) =>
    `Judgement record ${number} of this modification is not reviewed. It is reviewed, or discarded, before the modification is submitted.`;

  /** A record of the modification that is not the override's: the linked panel's own. */
  function other(status: string) {
    return judgementRecord({
      id: OTHER_ID,
      judgement_no: "JDG-000013",
      topic: "OTHER",
      status: status as ReturnType<typeof judgementRecord>["status"],
      conclusion: "The change order is the customer's standard form.",
    });
  }

  /** The texts of a table's header cells and of its body rows, cell by cell. */
  function tableTexts(table: HTMLElement): { headers: string[]; rows: string[][] } {
    const text = (cell: Element) => (cell.textContent ?? "").replace(/\s+/g, " ").trim();
    return {
      headers: Array.from(table.querySelectorAll("thead th"), text),
      rows: Array.from(table.querySelectorAll("tbody tr"), (row) =>
        Array.from(row.querySelectorAll("th, td"), text),
      ),
    };
  }

  it("a draft record left behind is discarded from Linked judgement records, and the column Actions stands only while a row has the command", async () => {
    serveWorkbench();
    const world = serveModification(classifiedRow(), [
      other("DRAFT"),
      judgementRecord({ status: "REVIEWED" }),
    ]);
    openStep("change");

    const table = await screen.findByRole("table", { name: "Linked judgement records" });
    expect(tableTexts(table)).toEqual({
      headers: ["Topic", "Conclusion", "Status", "Actions"],
      rows: [
        [
          "OtherJDG-000013",
          "The change order is the customer's standard form.",
          "Draft",
          "Discard",
        ],
        [
          "Modification treatment overrideJDG-000012",
          "The added seats change the pricing of the remaining seats.",
          "Reviewed",
          "",
        ],
      ],
    });

    fireEvent.click(within(table).getByRole("button", { name: "Discard" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Discard this draft record?" });
    expect(dialog.getAttribute("data-testid")).toBe("SF-07-dialog-discard-record");
    expect(world.requests).toEqual([]);
    fireEvent.click(within(dialog).getByRole("button", { name: "Discard" }));

    expect(await screen.findByText("Record JDG-000013 was discarded.")).toBeTruthy();
    // The discard takes no body and is the one command sent.
    expect(world.requests).toEqual([
      { method: "POST", path: `/judgements/${OTHER_ID}/discard`, body: null },
    ]);
    // The record keeps its row and reads Void; no row has a command, so the column is gone.
    await waitFor(() =>
      expect(tableTexts(screen.getByRole("table", { name: "Linked judgement records" }))).toEqual({
        headers: ["Topic", "Conclusion", "Status"],
        rows: [
          ["OtherJDG-000013", "The change order is the customer's standard form.", "Void"],
          [
            "Modification treatment overrideJDG-000012",
            "The added seats change the pricing of the remaining seats.",
            "Reviewed",
          ],
        ],
      }),
    );
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
  });

  // SCREENS §7.4 (rev 1.74; PRD SM-10 rev 1.199; 04 rev 1.296): the discard takes a rejected record
  // as it takes a draft. The record that a new one replaced had no command on any screen.
  it("a rejected record is discarded from Linked judgement records as a draft is", async () => {
    serveWorkbench();
    const world = serveModification(classifiedRow(), [
      other("REJECTED"),
      judgementRecord({ status: "REVIEWED" }),
    ]);
    openStep("change");

    const table = await screen.findByRole("table", { name: "Linked judgement records" });
    expect(tableTexts(table)).toEqual({
      headers: ["Topic", "Conclusion", "Status", "Actions"],
      rows: [
        [
          "OtherJDG-000013",
          "The change order is the customer's standard form.",
          "Rejected",
          "Discard",
        ],
        [
          "Modification treatment overrideJDG-000012",
          "The added seats change the pricing of the remaining seats.",
          "Reviewed",
          "",
        ],
      ],
    });

    fireEvent.click(within(table).getByRole("button", { name: "Discard" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Discard this rejected record?",
    });
    expect(world.requests).toEqual([]);
    fireEvent.click(within(dialog).getByRole("button", { name: "Discard" }));

    expect(await screen.findByText("Record JDG-000013 was discarded.")).toBeTruthy();
    expect(world.requests).toEqual([
      { method: "POST", path: `/judgements/${OTHER_ID}/discard`, body: null },
    ]);
    // The record keeps its row and reads Void; no row has a command, so the column is gone.
    await waitFor(() =>
      expect(tableTexts(screen.getByRole("table", { name: "Linked judgement records" }))).toEqual({
        headers: ["Topic", "Conclusion", "Status"],
        rows: [
          ["OtherJDG-000013", "The change order is the customer's standard form.", "Void"],
          [
            "Modification treatment overrideJDG-000012",
            "The added seats change the pricing of the remaining seats.",
            "Reviewed",
          ],
        ],
      }),
    );
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
  });

  it("a refused discard is shown in the confirmation, and a member without judgement.create for the contract's entity is offered none", async () => {
    serveWorkbench();
    const world = serveModification(classifiedRow(), [other("DRAFT")]);
    // The API's refusal of a record that is no draft any more — another member sent it for review
    // since the list was read.
    world.refuse.judgementDiscard = notDiscardable;
    openStep("change");

    const table = await screen.findByRole("table", { name: "Linked judgement records" });
    fireEvent.click(within(table).getByRole("button", { name: "Discard" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Discard this draft record?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Discard" }));
    const refusal = await within(dialog).findByRole("alert");
    expect(
      within(refusal).getByRole("heading", { name: "Action not available in this state" }),
    ).toBeTruthy();
    expect(within(refusal).getAllByText(NOT_DISCARDABLE)).toHaveLength(1);
    expect(screen.queryByText("Record JDG-000013 was discarded.")).toBeNull();
    expect(world.sent("POST", `/judgements/${OTHER_ID}/discard`)).toHaveLength(1);
    expect(world.judgements.map((item) => item.status)).toEqual(["DRAFT"]);
    cleanup();
    server.resetHandlers();

    // SCREENS §0.6 SCR-PERM-02 (a): the record is one of the contract's legal entity. A holder for
    // another entity reads the draft's row and is offered no command — the column is not there.
    serveWorkbench();
    serveModification(classifiedRow(), [other("DRAFT")]);
    openStep(
      "change",
      signedInMe({
        permissions: [
          "contract.read",
          "config.read",
          "ssp.read",
          "modification.create",
          "judgement.create",
        ],
        permission_scopes: {
          "contract.read": "*",
          "config.read": "*",
          "ssp.read": "*",
          "modification.create": "*",
          "judgement.create": ["0a1b2c3d-4e5f-4a6b-8c7d-0000000000ff"],
        },
      }),
    );
    expect(
      tableTexts(await screen.findByRole("table", { name: "Linked judgement records" })),
    ).toEqual({
      headers: ["Topic", "Conclusion", "Status"],
      rows: [["OtherJDG-000013", "The change order is the customer's standard form.", "Draft"]],
    });
    expect(screen.queryByRole("button", { name: "Discard" })).toBeNull();
  });

  it("the override banner offers Record judgement again once its record is rejected or discarded, and Discard while it is a draft", async () => {
    const BLOCKED = "Record the judgement to continue.";
    // What the banner says of the linked record, which command it offers, and whether "Next" waits.
    const states: readonly (readonly [string, string, string | null, boolean])[] = [
      ["SUBMITTED", "Judgement record JDG-000012: Waiting for review.", null, false],
      ["REVIEWED", "Judgement record JDG-000012: Reviewed.", null, false],
      ["REJECTED", "Judgement record JDG-000012: Rejected.", "Record judgement", true],
      ["VOIDED", "Judgement record JDG-000012: Void.", "Record judgement", true],
      ["DRAFT", "Judgement record JDG-000012: Draft.", "Discard", true],
    ];
    for (const [status, line, command, waits] of states) {
      serveWorkbench();
      serveModification(classifiedRow(DEPARTING), [
        judgementRecord({ status: status as ReturnType<typeof judgementRecord>["status"] }),
      ]);
      openStep("treatment");
      const banner = await screen.findByTestId("SF-07-banner-override");
      expect(await within(banner).findByText(line)).toBeTruthy();
      expect(
        within(banner)
          .queryAllByRole("button")
          .map((button) => button.textContent),
      ).toEqual(command === null ? [] : [command]);
      expect(screen.queryByTestId("SF-07-blocked")?.textContent ?? null).toBe(
        waits ? BLOCKED : null,
      );
      cleanup();
      server.resetHandlers();
    }

    // The draft is discarded from the banner: it reads Void then, and a new record is offered.
    serveWorkbench();
    const world = serveModification(classifiedRow(DEPARTING), [judgementRecord()]);
    openStep("treatment");
    const banner = await screen.findByTestId("SF-07-banner-override");
    fireEvent.click(await within(banner).findByRole("button", { name: "Discard" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Discard this draft record?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Discard" }));
    expect(await screen.findByText("Record JDG-000012 was discarded.")).toBeTruthy();
    expect(world.sent("POST", `/judgements/${JUDGEMENT_ID}/discard`)).toHaveLength(1);
    const after = await screen.findByTestId("SF-07-banner-override");
    expect(await within(after).findByText("Judgement record JDG-000012: Void.")).toBeTruthy();
    expect(await within(after).findByRole("button", { name: "Record judgement" })).toBeTruthy();
    expect(within(after).queryByRole("button", { name: "Discard" })).toBeNull();
  });

  it("Submit for approval waits while a judgement record of the modification is a draft or waits for review, and shows the API's refusal as it comes", async () => {
    serveWorkbench();
    const world = serveModification(previewedRow(), [other("DRAFT")]);
    const { queryClient } = openStep("submit");
    const submit = () => screen.getByRole("button", { name: "Submit for approval" });
    const reread = () => queryClient.invalidateQueries({ queryKey: ["modification-judgements"] });

    // PRD ERR-95: the record is reviewed, or discarded, first. The first of them is named.
    expect((await screen.findByTestId("SF-07-blocked")).textContent).toBe(ERR_95("JDG-000013"));
    expect(submit().getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(submit());
    expect(world.sent("POST", "/submit")).toHaveLength(0);
    // The summary names the record with its status in the shared words.
    const summary = screen.getByTestId("SF-07-summary");
    expect(within(summary).getByText(/Other · Draft/)).toBeTruthy();

    world.judgements = [other("SUBMITTED")];
    await reread();
    await waitFor(() =>
      expect(within(summary).getByText(/Other · Waiting for review/)).toBeTruthy(),
    );
    expect(screen.getByTestId("SF-07-blocked").textContent).toBe(ERR_95("JDG-000013"));
    expect(submit().getAttribute("aria-disabled")).toBe("true");

    // A rejected, a superseded and a discarded record hold nothing.
    for (const status of ["REJECTED", "SUPERSEDED", "VOIDED"]) {
      world.judgements = [other(status)];
      await reread();
      await waitFor(() => expect(screen.queryByTestId("SF-07-blocked")).toBeNull());
      expect(submit().getAttribute("aria-disabled")).toBeNull();
    }

    // The API's refusal stays the backstop — a record added since the list was read — and comes as
    // PRD ERR-87 does: entries without a field, each shown.
    world.refuse.submit = () => recordsNotReviewed(["JDG-000014", "JDG-000015"]);
    fireEvent.click(submit());
    expect(await screen.findByText(ERR_95("JDG-000014"))).toBeTruthy();
    expect(screen.getByText(ERR_95("JDG-000015"))).toBeTruthy();
    expect(world.row.status).toBe("DRAFT");
  });

  it("a departing treatment whose record was discarded holds the submission with the record's status", async () => {
    serveWorkbench();
    const world = serveModification(previewedRow(DEPARTING), [
      judgementRecord({ status: "VOIDED" }),
    ]);
    openStep("submit");

    expect((await screen.findByTestId("SF-07-blocked")).textContent).toBe(
      "Judgement record JDG-000012 is not reviewed (Void). Record a new one in step Treatment, or choose the proposed treatment.",
    );
    const submit = screen.getByRole("button", { name: "Submit for approval" });
    expect(submit.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(submit);
    expect(world.sent("POST", "/submit")).toHaveLength(0);
  });
});

// SCREENS §7.7 and §7.9 (rev 1.77; lane QA-BE's item MOD-PREVIEW-READ-SCOPE-1 on the screens; 04 §16.10
// rev 1.300 "Who reads a stored preview"): the API answers a stored preview to a member who holds
// `contract.read` for every entity of the contract's combination group, and tells every other reader
// of the row that one is stored — `impact_preview` null with `impact_preview_withheld` true. The
// wizard read such a row as one without a preview. The stand-in answers as measured through the routes
// (register index 276).
describe("SF-07 a stored preview the reader is not shown", () => {
  const TITLE = "You are not shown this preview";
  const TEXT =
    "The stored preview holds figures of legal entities outside your access. It is shown to people whose access covers every entity of the contract's combination group.";
  // DS-FMT-05: money outside a grid reads ISO code, no-break space, amount.
  const NBSP = String.fromCharCode(160);
  const CATCH_UP = `Catch-up of this contract's obligations: USD${NBSP}+1,906.79.`;
  // 04 §16.10 rev 1.295: what the API answers a member whose roles do not reach every entity.
  const NO_PREVIEW =
    "This item belongs to legal entities outside your roles, so you cannot preview it.";
  const NO_SUBMISSION =
    "This item belongs to legal entities outside your roles, so you cannot submit it for approval.";
  const outside = (detail: string) => () =>
    problemResponse("forbidden", 403, "Permission denied", { code: null, detail });

  /** The classified draft with a stored preview whose catch-up is 1,906.79. */
  function stored(overrides: Partial<Modification> = {}): Modification {
    return previewedRow({
      impact_preview: { ...PREVIEW, catch_up_total: money("1906.79") },
      impact_summary: { catch_up_total: money("1906.79") },
      ...overrides,
    });
  }

  /** The time a request that must not be sent would take to be sent. */
  function pause(): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, 50));
  }

  it("a stored preview the reader is not shown stands on step 4 as a notice with the catch-up: nothing is run, no Run preview, and Next goes on", async () => {
    serveWorkbench();
    const world = serveModification(stored());
    world.previewWithheld = true;
    // The member the preview route refuses: a run would show its sentence.
    world.refuse.preview = outside(NO_PREVIEW);
    const rendered = openStep("preview");

    const notice = await screen.findByTestId("SF-07-banner-preview-withheld");
    expect(within(notice).getByRole("heading", { level: 3, name: TITLE })).toBeTruthy();
    expect(notice.textContent).toBe(`${TITLE}${TEXT}${CATCH_UP}`);
    // An info banner (DS-CMP-29): nothing went wrong. It stood there when the step opened: no live
    // region.
    expect(notice.querySelector("[data-tone]")?.getAttribute("data-tone")).toBe("info");
    expect(within(notice).queryByRole("status")).toBeNull();
    // The step is done for the stepper, with the catch-up the API answers to every reader of the row.
    expect(stepNames()[3]).toBe("Step 4 of 5, Impact preview, Catch-up +1,906.79");
    expect(screen.queryByRole("region", { name: /^Impact summary/ })).toBeNull();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByRole("button", { name: "Run preview" })).toBeNull();
    expect(screen.queryByTestId("SF-07-blocked")).toBeNull();
    expect(next().getAttribute("aria-disabled")).toBeNull();
    await pause();
    expect(world.sent("POST", "/preview")).toEqual([]);
    expect(world.sent("POST", "/classify")).toEqual([]);
    expect(screen.queryByText(NO_PREVIEW)).toBeNull();
    expect(screen.queryByText(STALE)).toBeNull();

    fireEvent.click(next());
    await waitFor(() => expect(rendered.router.state.location.search).toContain("step=submit"));
    expect(await screen.findByTestId("SF-07-summary")).toBeTruthy();
  });

  it("a preview the step ran and the read then withholds ends the wait: one run, the notice announced, and Next goes on", async () => {
    serveWorkbench();
    // The member the route takes and the read does not answer: the job succeeds and stores the
    // preview, and the row comes back without it.
    const world = serveModification(classifiedRow());
    world.previewWithheld = true;
    openStep("preview");

    const notice = await screen.findByTestId("SF-07-banner-preview-withheld");
    expect(notice.textContent).toBe(
      `${TITLE}${TEXT}Catch-up of this contract's obligations: USD${NBSP}0.00.`,
    );
    // It follows the run of this step: inserted after load, and announced.
    expect(within(notice).getByRole("status").textContent).toContain(TITLE);
    expect(world.row.impact_preview).not.toBeNull();
    expect(screen.queryByText("Calculating preview")).toBeNull();
    expect(screen.queryByRole("progressbar", { name: "Calculating preview" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Run preview" })).toBeNull();
    await waitFor(() => expect(screen.queryByTestId("SF-07-blocked")).toBeNull());
    expect(next().getAttribute("aria-disabled")).toBeNull();
    await pause();
    expect(world.sent("POST", "/preview")).toHaveLength(1);
  });

  it("a draft whose stored preview the reader is not shown is submitted as any other: the API's refusal is shown as it comes, and the detail says of the preview what step 4 said", async () => {
    serveWorkbench();
    const world = serveModification(stored());
    world.previewWithheld = true;
    world.refuse.submit = outside(NO_SUBMISSION);
    openStep("submit");

    // The row holds a stored preview: the last step is open, and nothing holds the command back.
    await screen.findByTestId("SF-07-summary");
    const submit = () => screen.getByRole("button", { name: "Submit for approval" });
    await waitFor(() => expect(submit().getAttribute("aria-disabled")).toBeNull());
    expect(screen.queryByTestId("SF-07-blocked")).toBeNull();
    fireEvent.click(submit());
    expect(await screen.findByText(NO_SUBMISSION)).toBeTruthy();
    expect(world.sent("POST", "/submit")).toHaveLength(1);
    expect(world.row.status).toBe("DRAFT");

    // A member the API takes the submission from: the answer withholds the preview as the read does.
    world.refuse.submit = null;
    fireEvent.click(submit());
    expect(
      await screen.findByText(
        "Submitted for approval. Request APR-000434 is waiting for approval.",
      ),
    ).toBeTruthy();
    expect(await screen.findByTestId("SF-07-detail-page")).toBeTruthy();
    const section = await screen.findByTestId("SF-07-section-preview");
    expect(within(section).getByTestId("SF-07-banner-preview-withheld").textContent).toBe(
      `${TITLE}${TEXT}${CATCH_UP}`,
    );
    expect(
      within(section).getByText("Snapshot e9ac7d5ea7aa reviewed by the approver."),
    ).toBeTruthy();
    expect(within(section).queryByText("No preview was stored.")).toBeNull();
  });

  it("a row that states no proposal and whose stored preview the reader is not shown is not classified again", async () => {
    serveWorkbench();
    // O1's answer is open and the row states no proposal: without a stored preview its proposals
    // are unknown and `/classify` is asked — which clears a stored preview for every reader.
    const world = serveModification(
      stored({ questionnaire: { O2: CONFIRMED_O2 }, prefill_reasons: {}, proposal_detail: {} }),
    );
    world.previewWithheld = true;
    openStep("questionnaire");

    await screen.findByRole("radiogroup", { name: /^Is the added price at SSP\?/ });
    await pause();
    expect(world.sent("POST", "/classify")).toEqual([]);
    expect(world.row.impact_preview).not.toBeNull();
    cleanup();
    server.resetHandlers();

    // The control: the same row without a stored preview is classified on opening.
    serveWorkbench();
    const bare = serveModification(
      classifiedRow({
        questionnaire: { O2: CONFIRMED_O2 },
        prefill_reasons: {},
        proposal_detail: {},
      }),
    );
    bare.previewWithheld = true;
    openStep("questionnaire");
    await waitFor(() => expect(bare.sent("POST", "/classify")).toHaveLength(1));
  });

  it("a stored preview the reader is not shown is out of date once an edit clears it, as any other", async () => {
    serveWorkbench();
    const world = serveModification(stored());
    world.previewWithheld = true;
    openStep("change");

    const scope = await screen.findByRole("textbox", { name: /^Scope description/ });
    expect(screen.queryByText(STALE)).toBeNull();
    expect(stepNames()[3]).toBe("Step 4 of 5, Impact preview, Catch-up +1,906.79");
    fireEvent.change(scope, {
      target: { value: "Marrowby adds 50 seats for the remaining term." },
    });
    fireEvent.click(next());
    expect(await screen.findByText(STALE)).toBeTruthy();
    expect(world.row.impact_preview).toBeNull();
    expect(stepNames()[3]).toBe("Step 4 of 5, Impact preview, not started");
  });
});
