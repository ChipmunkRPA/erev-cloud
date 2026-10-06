// Section A of the pass: one contract from draft to revenue (PRD J-03; SCREENS §4.10, §4.1.3 "Step
// 1 path", §4.9.1). maya books a draft on SF-03:new — one subscription line of AVM-PLAT-100 for
// AVM-US, USD 120,000.00 from 01 Sep 2026 to 31 Aug 2027 —, records the Step 1 review, priya reviews
// it, maya records the assessment and submits the contract, priya approves the activation. Then the
// September amount of its obligation is read from every place that states it: the workbench's
// Schedules tab, Schedules (SF-04), the revenue waterfall and the schedule lines of the API. Each
// step is taken on the screen first; the rule of the pass for a step that does not get there is in
// `steps.ts`.
import { randomUUID } from "node:crypto";

import type { Page } from "@playwright/test";

import { Api, at, cents, decimal, grouped, items, text } from "../api";
import type { Qa } from "../fixtures";
import { flat, type Outcome } from "../record";
import { arrive, patchState, readState } from "../sessions";
import {
  approveOnScreen,
  dismissToasts,
  figures,
  flowStep,
  modal,
  scrolledRow,
  toasts,
} from "../steps";
import { BOOK, makeWaterfallRun, reportRows, SEPTEMBER } from "../world";

const ENTITY = "AVM-US";
const CONTEXT = `entity=${ENTITY}&period=${SEPTEMBER}&book=${BOOK}`;
const PRICE = "120000.00";
/** 120,000.00 over 365 days, 30 of them in September, half-up to the cent. */
const SEPTEMBER_AMOUNT = "9863.01";

async function contractOf(api: Api, externalId: string): Promise<unknown> {
  const listed = await api.list("/api/v1/contracts", { q: externalId });
  return listed.find((item) => text(item, "external_id") === externalId);
}

async function latestReview(api: Api, contractId: string): Promise<unknown> {
  const listed = await api.get("/api/v1/judgements", {
    subject_type: "contract",
    subject_id: contractId,
    limit: 50,
  });
  return at(listed.json, "items", 0);
}

/** The September revenue lines of the contract's obligation O1, as the API states them. */
async function septemberLines(api: Api, contractId: string): Promise<readonly unknown[]> {
  const got = await api.get("/api/v1/schedule-lines", {
    contract: contractId,
    schedule_kind: "REVENUE",
    book: BOOK,
    from_period: SEPTEMBER,
    to_period: SEPTEMBER,
    limit: 200,
  });
  // The obligation's own line of the month: a catch-up of an activation is a line of its own.
  return items(got.json).filter(
    (line) => text(line, "obligation_key") === "O1" && text(line, "line_type") === "NORMAL",
  );
}

async function tie(maya: Page, api: Api, contractId: string, externalId: string): Promise<Outcome> {
  // The computation of an approved activation is a job: the schedule is read once it holds lines.
  let lines: readonly unknown[] = [];
  for (let turn = 0; turn < 120 && lines.length === 0; turn += 1) {
    lines = await septemberLines(api, contractId);
    if (lines.length === 0) {
      await new Promise((resolve) => setTimeout(resolve, 1_000));
    }
  }
  if (lines.length === 0) {
    const contract = (await api.get(`/api/v1/contracts/${contractId}`)).json;
    return {
      observed: `the contract is ${text(contract, "status")} and holds no revenue line for ${SEPTEMBER} two minutes after its activation`,
      result: "FINDING",
      finding: "stopped flow",
    };
  }
  let sum = 0n;
  for (const line of lines) {
    sum += cents(text(line, "amount", "amount")) ?? 0n;
  }
  const api9 = decimal(sum);
  const expected = `USD ${grouped(api9)}`;
  const places: string[] = [`schedule lines of the API: ${String(lines.length)} line(s), ${api9}`];
  // A figure a place states and that differs is wrong; a figure the pass did not find on a screen
  // is not read, which is said and is no finding.
  const wrong: string[] = [];
  const unread: string[] = [];
  if (cents(api9) !== cents(SEPTEMBER_AMOUNT)) {
    wrong.push(
      `the API's September amount is ${api9}; 120,000.00 × 30 / 365 is ${SEPTEMBER_AMOUNT}`,
    );
  }

  // The workbench: the key figures, then the Schedules tab.
  await maya.goto(`/contracts/${contractId}/obligations?${CONTEXT}`);
  const strip = maya.getByTestId("SF-03-kpi-strip");
  await strip.waitFor({ state: "visible", timeout: 30_000 });
  const contract = (await api.get(`/api/v1/contracts/${contractId}`)).json;
  const price = (await figures(strip)).find((figure) => /^Transaction price/.test(figure.label));
  const priceApi = `USD ${grouped(text(contract, "kpis", "transaction_price", "amount"))}`;
  places.push(
    `workbench key figure Transaction price: screen "${price?.value ?? "none"}", API ${priceApi}`,
  );
  if (price === undefined) {
    unread.push("the workbench's Transaction price key figure was not found");
  }
  if (
    (price !== undefined && price.value !== priceApi) ||
    cents(text(contract, "kpis", "transaction_price", "amount")) !== cents(PRICE)
  ) {
    wrong.push(
      `Transaction price: screen "${price?.value ?? "none"}", API ${priceApi}, booked ${PRICE}`,
    );
  }
  await maya.goto(`/contracts/${contractId}/schedules?${CONTEXT}`);
  const schedule = maya
    .getByTestId("SF-03-grid-revenue-schedule")
    .getByRole("grid", { name: "Revenue schedule" });
  await schedule.waitFor({ state: "visible", timeout: 30_000 });
  // The grid is there before its rows are: the month's row is waited for before it is read.
  await schedule
    .getByRole("row")
    .filter({ hasText: "Sep 2026" })
    .first()
    .waitFor({ state: "visible", timeout: 20_000 })
    .catch(() => undefined);
  const tab = (await figures(schedule)).filter((figure) => figure.label.includes("Sep 2026"));
  places.push(
    `workbench Schedules tab: ${tab.map((figure) => `"${figure.label}" ${figure.value}`).join(", ") || "no figure for Sep 2026"}`,
  );
  if (tab.length === 0) {
    unread.push("the Schedules tab showed no figure named for Sep 2026");
  } else if (!tab.some((figure) => figure.value === expected)) {
    wrong.push(
      `the Schedules tab states ${tab.map((figure) => figure.value).join(", ")} for Sep 2026, not ${expected}`,
    );
  }

  // Schedules (SF-04), by obligation.
  await maya.goto(`/schedules?${CONTEXT}&rows=obligation`);
  await maya.waitForURL(/[?&]run=[0-9a-f-]{36}(&|$)/, { timeout: 60_000 }).catch(() => undefined);
  const grid = maya
    .getByTestId("SF-04-grid-waterfall")
    .getByRole("grid", { name: "Revenue waterfall" });
  await grid.waitFor({ state: "visible", timeout: 60_000 }).catch(() => undefined);
  const key = externalId.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  const row = await scrolledRow(maya, grid, `SF-04-row-${key}-o1`);
  const listed =
    row === null
      ? []
      : (await figures(row)).filter((figure) => figure.label.startsWith("Sep 2026"));
  places.push(
    `Schedules (SF-04): ${row === null ? "the obligation's row is not in the grid" : listed.map((figure) => figure.value).join(", ") || "no figure for Sep 2026"}`,
  );
  if (listed.length === 0) {
    unread.push(
      row === null
        ? "Schedules (SF-04) showed no row of the obligation"
        : "the obligation's row on Schedules (SF-04) showed no figure named for Sep 2026",
    );
  } else if (!listed.some((figure) => figure.value === expected)) {
    wrong.push(
      `Schedules (SF-04) states ${listed.map((figure) => figure.value).join(", ")} for the obligation in Sep 2026, not ${expected}`,
    );
  }

  // The revenue waterfall of the month, by contract.
  const run = await makeWaterfallRun(api, [ENTITY], SEPTEMBER, SEPTEMBER);
  const rows = run.id === "" ? [] : await reportRows(api, run.id);
  const mine = rows.find((item) => text(item, "row_key").endsWith(externalId));
  const waterfall = text(mine, `period:${SEPTEMBER}`, "amount");
  places.push(
    `revenue waterfall (${run.said}): ${mine === undefined ? "no row of the contract" : waterfall}`,
  );
  if (run.id === "") {
    unread.push(`the waterfall of the month was not run (${run.said})`);
  } else if (cents(waterfall) !== cents(api9)) {
    wrong.push(
      `the waterfall's row says ${waterfall === "" ? "nothing of the contract" : waterfall}`,
    );
  }
  const observed = `${externalId}, September 2026: ${places.join("; ")}`;
  if (wrong.length > 0) {
    return {
      observed: `THE PLACES DISAGREE: ${wrong.join(" | ")}. ${observed}`,
      result: "FINDING",
      finding: "wrong figure",
      page: maya,
    };
  }
  return unread.length === 0
    ? { observed, result: "pass", page: maya }
    : {
        observed: `no place disagrees; not every place was read: ${unread.join(" | ")}. ${observed}`,
        result: "seen once",
        page: maya,
      };
}

export async function contractSection({ record, sessions }: Qa): Promise<void> {
  const maya = await sessions.page("maya");
  const priya = await sessions.page("priya");
  const api = new Api(maya);
  const reviewer = new Api(priya);
  const known = readState().contract;
  const externalId = known?.externalId ?? `QA-RC-${randomUUID().slice(0, 8).toUpperCase()}`;
  let contractId = known?.id ?? "";
  const workbench = () => `/contracts/${contractId}/obligations?${CONTEXT}&step=1`;
  const status = async () =>
    text((await api.get(`/api/v1/contracts/${contractId}`)).json, "status");

  const booked = await flowStep(record, {
    head: {
      check: "A-1 a draft on SF-03:new",
      persona: "maya",
      address: `/contracts/new?${CONTEXT}`,
      expected:
        'The form takes the external id, the customer on file, the contracting entity, the dates and one line; "Save draft" books the draft and opens its workbench (03 REQ-CON-018; SCREENS §4.10)',
    },
    page: maya,
    screen: async () => {
      await maya.goto(`/contracts/new?${CONTEXT}`);
      const grid = maya
        .getByTestId("SF-03-grid-lines")
        .getByRole("grid", { name: "Contract lines" });
      await grid.waitFor({ state: "visible", timeout: 30_000 });
      await maya.getByRole("textbox", { name: "External id" }).fill(externalId);
      await maya.getByRole("combobox", { name: "Customer" }).fill("Pellworth");
      await maya
        .getByRole("listbox", { name: "Customer" })
        .getByRole("option", { name: /^Pellworth Logistics/ })
        .click();
      await maya.getByRole("combobox", { name: "Contracting entity" }).click();
      await maya
        .getByRole("listbox", { name: "Contracting entity" })
        .getByRole("option", { name: new RegExp(`^${ENTITY} `) })
        .click();
      await maya.getByRole("textbox", { name: "Inception date" }).fill("2026-09-01");
      await maya.getByRole("textbox", { name: "Contract reference" }).fill(`MSA-${externalId}`);
      await grid.getByRole("combobox", { name: "Product, line 1" }).fill("AVM-PLAT-100");
      await maya
        .getByTestId("SF-03-grid-lines")
        .getByRole("listbox", { name: "Product, line 1" })
        .getByRole("option", { name: /^AVM-PLAT-100 / })
        .click();
      // A line is saved with its quantity (lib/forms/contract.ts: an empty one is a field error).
      await grid.getByRole("textbox", { name: "Quantity, line 1" }).fill("1");
      await grid.getByRole("textbox", { name: "Total price, line 1" }).fill("120000");
      await grid.getByRole("textbox", { name: "Start date, line 1" }).fill("2026-09-01");
      await grid.getByRole("textbox", { name: "End date, line 1" }).fill("2027-08-31");
      await maya.getByRole("button", { name: "Save draft" }).click();
      await arrive(maya, (url) => /\/contracts\/[0-9a-f-]{36}\/obligations/.test(url.pathname));
      return `saved; the workbench opened at ${new URL(maya.url()).pathname.replace(/[0-9a-f]{8}-[0-9a-f-]{27}/, "<id>")}; messages [${(await toasts(maya)).join(" | ")}]`;
    },
    reached: async () => {
      const contract = await contractOf(api, externalId);
      if (contract === undefined) {
        return `no contract ${externalId} is listed`;
      }
      contractId = text(contract, "id");
      patchState({ contract: { id: contractId, externalId } });
      return null;
    },
  });
  if (!booked) {
    return;
  }

  const RATIONALE = "Booked for the QA pass: not negotiated as a package with another contract.";
  const openSuggestions = async () =>
    items(
      (await api.get("/api/v1/combination-suggestions", { contract: contractId, limit: 200 })).json,
    );
  await flowStep(record, {
    head: {
      check: "A-2 combination suggestions of the draft",
      persona: "maya",
      address: workbench(),
      expected:
        'Step 1 lists the open suggestions with "Dismiss suggestion"; each is dismissed with a rationale, since the activation checklist refuses while one is open (PRD BR-CON-01; SCREENS §4.9.7)',
    },
    page: maya,
    screen: async () => {
      const before = (await openSuggestions()).length;
      await maya.goto(workbench());
      for (let turn = 0; turn < before; turn += 1) {
        await maya.getByRole("button", { name: "Dismiss suggestion" }).first().click();
        const dialog = modal(maya, "Dismiss suggestion");
        await dialog.getByRole("textbox").first().fill(RATIONALE);
        await dialog.getByRole("button", { name: "Dismiss suggestion" }).click();
        await maya
          .getByText("Suggestion dismissed.")
          .first()
          .waitFor({ state: "visible", timeout: 20_000 });
        await dialog.waitFor({ state: "hidden", timeout: 10_000 }).catch(() => undefined);
        await dismissToasts(maya);
      }
      return `${String(before)} suggestion(s) dismissed on the screen`;
    },
    reached: async () => {
      const left = (await openSuggestions()).length;
      return left === 0 ? null : `${String(left)} combination suggestion(s) of the draft are open`;
    },
    api: async () => {
      let last = await api.get("/api/v1/combination-suggestions", { contract: contractId });
      for (const suggestion of await openSuggestions()) {
        last = await api.send(
          "POST",
          `/api/v1/combination-suggestions/${text(suggestion, "id")}/dismiss`,
          { rationale: RATIONALE },
        );
      }
      return last;
    },
  });

  const reviewed = await flowStep(record, {
    head: {
      check: "A-3 the Step 1 review, submitted",
      persona: "maya",
      address: workbench(),
      expected:
        'Step 1 says "No Step 1 review is recorded." and offers "Record Step 1 review"; the five criteria and a rationale are submitted for review (PRD J-03.3; SCREENS §4.9.1)',
    },
    page: maya,
    screen: async () => {
      await maya.goto(workbench());
      const line = maya.getByTestId("SF-03-step1-path");
      await line.waitFor({ state: "visible", timeout: 30_000 });
      const said = flat(await line.innerText(), 200);
      await line.getByRole("button", { name: "Record Step 1 review" }).click();
      const drawer = maya.getByRole("dialog", { name: "Record Step 1 review" });
      for (const legend of [
        /^Approved and committed/,
        /^Rights identified/,
        /^Payment terms identified/,
        /^Commercial substance/,
        /^Collectibility probable/,
      ]) {
        await drawer
          .getByRole("group", { name: legend })
          .getByRole("radio", { name: "Yes" })
          .check();
      }
      await drawer
        .getByLabel(/^Rationale/)
        .fill("The customer is on file with a clean payment record; the order is signed.");
      await drawer.getByRole("button", { name: "Submit for review" }).click();
      const toast = maya.getByText(/^Step 1 review JDG-\d+ submitted for review\.$/);
      await toast.first().waitFor({ state: "visible", timeout: 30_000 });
      return `the line read "${said}"; then "${flat(await toast.first().innerText(), 120)}"`;
    },
    reached: async () => {
      const review = await latestReview(api, contractId);
      return review !== undefined && ["SUBMITTED", "REVIEWED"].includes(text(review, "status"))
        ? null
        : `the latest Step 1 record is ${review === undefined ? "none" : text(review, "status")}`;
    },
  });
  if (!reviewed) {
    return;
  }

  const approvedReview = await flowStep(record, {
    head: {
      check: "A-4 the Step 1 review, reviewed",
      persona: "priya",
      address: "/approvals/requests/<the judgement record's request>",
      expected:
        "A Revenue Reviewer decides the record with a fresh code (PRD J-03.3a, BR-PLT-06); the record is REVIEWED",
    },
    page: priya,
    screen: async () => {
      const review = await latestReview(api, contractId);
      const decided = await approveOnScreen(
        priya,
        "priya",
        text(review, "approval_request_id"),
        "Reviewed the Step 1 conclusion and its evidence.",
      );
      return `${text(review, "judgement_no")}: ${decided.stepUp ? "a code was asked" : "no code was asked"}; "${decided.toast}"`;
    },
    reached: async () => {
      const review = await latestReview(reviewer, contractId);
      return text(review, "status") === "REVIEWED"
        ? null
        : `the record is ${text(review, "status")}`;
    },
  });
  if (!approvedReview) {
    return;
  }

  const assessed = await flowStep(record, {
    head: {
      check: "A-5 the assessment",
      persona: "maya",
      address: workbench(),
      expected:
        'Step 1 says the record was reviewed and offers "Record assessment"; the drawer cites the record and both books at the inception date; the assessment is recorded (PRD J-03.3b)',
    },
    page: maya,
    screen: async () => {
      await maya.goto(workbench());
      const line = maya.getByTestId("SF-03-step1-path");
      await line.waitFor({ state: "visible", timeout: 30_000 });
      const said = flat(await line.innerText(), 240);
      await line.getByRole("button", { name: "Record assessment" }).click();
      const drawer = maya.getByRole("dialog", { name: "Record assessment" });
      const body = flat(await drawer.innerText(), 300);
      await drawer.getByRole("button", { name: "Record assessment" }).click();
      await maya
        .getByText("Assessment recorded.")
        .first()
        .waitFor({ state: "visible", timeout: 30_000 });
      return `the line read "${said}"; the drawer read "${body}"; then "Assessment recorded."`;
    },
    reached: async () => {
      const events = await api.get(`/api/v1/contracts/${contractId}/events`, {
        event_type: "COLLECTIBILITY_ASSESSED",
        limit: 5,
      });
      return items(events.json).length > 0
        ? null
        : "the contract holds no COLLECTIBILITY_ASSESSED event";
    },
  });
  if (!assessed) {
    return;
  }

  const submitted = await flowStep(record, {
    head: {
      check: "A-6 submitted for activation",
      persona: "maya",
      address: workbench(),
      expected:
        '"Submit for activation" sends the draft to its approver; the activation checklist names what is still missing when it refuses (PRD J-03.8; SCREENS §4.1.6)',
    },
    page: maya,
    screen: async () => {
      await maya.goto(workbench());
      await maya.getByRole("button", { name: "Submit for activation" }).first().click();
      const done = maya.getByText(/^(Submitted for activation\.|Contract activated\.)/);
      const refused = maya.getByText("Contract cannot be activated");
      await done.or(refused).first().waitFor({ state: "visible", timeout: 60_000 });
      if (
        await refused
          .first()
          .isVisible()
          .catch(() => false)
      ) {
        const checklist = (await api.get(`/api/v1/contracts/${contractId}/activation-checklist`))
          .json;
        const failing = items(checklist)
          .filter((item) => at(item, "passed") !== true)
          .map((item) => `${text(item, "code")}: ${text(item, "detail")}`);
        return `refused: "Contract cannot be activated"; the checklist's open items: ${failing.join("; ")}`;
      }
      return `"${flat(await done.first().innerText(), 160)}"`;
    },
    reached: async () =>
      ["PENDING_REVIEW", "ACTIVE"].includes(await status())
        ? null
        : `the contract is ${await status()}`,
    api: async () => {
      const contract = (await api.get(`/api/v1/contracts/${contractId}`)).json;
      return api.send(
        "POST",
        `/api/v1/contracts/${contractId}/submit-activation`,
        {},
        { "If-Match": `"s${text(contract, "head_stream_version")}"` },
      );
    },
  });
  if (!submitted) {
    return;
  }

  const active = await flowStep(record, {
    head: {
      check: "A-7 the activation, approved",
      persona: "priya",
      address: "/approvals/requests/<the activation request>",
      expected:
        "priya, who did not prepare the contract, approves the activation with a fresh code (03 REQ-PLT-011; BR-PLT-06); the contract is ACTIVE (PRD J-03.9)",
    },
    page: priya,
    screen: async () => {
      const pending = await reviewer.list("/api/v1/approvals", {
        status: "PENDING",
        subject_type: "CONTRACT_ACTIVATION",
      });
      const request = pending.find((item) => text(item, "subject", "id") === contractId);
      if (request === undefined) {
        return `no pending activation request of the contract among ${String(pending.length)}`;
      }
      const decided = await approveOnScreen(
        priya,
        "priya",
        text(request, "id"),
        "Read the terms, the allocation and the impact preview.",
      );
      return `${text(request, "request_no")} "${text(request, "summary")}": ${decided.stepUp ? "a code was asked" : "no code was asked"}; "${decided.toast}"`;
    },
    reached: async () =>
      (await status()) === "ACTIVE" ? null : `the contract is ${await status()}`,
  });
  if (!active) {
    return;
  }

  await record.check(
    {
      check: "A-8 the obligation's September amount, every place",
      persona: "maya",
      address: `/contracts/<id>/schedules, /schedules?${CONTEXT}&rows=obligation, revenue_waterfall`,
      expected: `One number: USD ${grouped(SEPTEMBER_AMOUNT)} (120,000.00 over 365 days, 30 in September) on the workbench's Schedules tab, on Schedules (SF-04), in the waterfall's row and in the API's schedule lines; the Transaction price key figure states USD ${grouped(PRICE)} (PRD E2E-02; REQ-UX-005)`,
    },
    () => tie(maya, api, contractId, externalId),
  );
}
