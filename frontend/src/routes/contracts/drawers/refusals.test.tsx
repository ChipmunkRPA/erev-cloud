// @vitest-environment jsdom
// The drawers of the contract workbench under a refused command (docs/dev-guide.md DG-FE-06; SCREENS
// §0.7 SCR-ST-13; item KIT-UNPLACED-ERRORS-1, head 2): a message of `errors[]` stands at the field that
// sends the member it names, and the banner lists what no field shows — it was shown nowhere.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import type { CombinationSuggestion, Contract } from "../../../lib/api/queries/contracts";
import type { Obligation, ObligationEvent } from "../../../lib/api/queries/obligations";
import { renderWithApp } from "../../../test/app";
import { apiUrl, installMswServer, server } from "../../../test/msw";
import {
  describedBy,
  RECORD_CHANGED,
  REFUSAL_REFERENCE,
  REFUSAL_TITLE as TITLE,
  refusedWith,
} from "../../../test/refusals";
import { CONTRACT_ID, workbenchContract, workbenchObligation } from "../../../test/workbench";
import { VoidEventModal } from "../obligation-pane";
import { CombineDrawer, DismissSuggestionModal } from "./combine";
import { DistinctReviewDrawer } from "./distinct-review";
import { DocumentsDrawer } from "./documents";
import { ApplyHoldDrawer } from "./holds";
import { EditMemosDrawer } from "./memos";
import { RecordEventDrawer } from "./record-event";

installMswServer();

afterEach(() => {
  cleanup();
});

const CONTRACT = workbenchContract() as unknown as Contract;
const O1 = workbenchObligation() as unknown as Obligation;
/** Picks an option of a Select inside `scope`. */
function select(scope: HTMLElement, name: RegExp, option: string): void {
  const trigger = within(scope).getByRole("combobox", { name });
  fireEvent.click(trigger);
  const list = document.getElementById(trigger.getAttribute("aria-controls") ?? "");
  if (list === null) {
    throw new Error(`The select ${String(name)} has no open list`);
  }
  fireEvent.mouseDown(within(list).getByRole("option", { name: option }));
}

describe("SF-03 Apply hold under a refused command", () => {
  const NO_FIELD = "Journal export holds are not offered while the contract is in draft.";
  const AT_REASON = "Say what the hold waits for.";

  function open(messages: Readonly<Record<string, string>>, status = 422) {
    server.use(
      http.post(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/apply-hold`), () =>
        refusedWith(messages, { status }),
      ),
    );
    renderWithApp(
      <ApplyHoldDrawer contract={CONTRACT} obligations={[O1]} onClose={() => undefined} />,
    );
  }

  async function send(): Promise<HTMLElement> {
    const drawer = await screen.findByRole("dialog", { name: "Apply hold" });
    fireEvent.change(within(drawer).getByLabelText(/^Reason/), {
      target: { value: "The customer disputes the September invoice." },
    });
    fireEvent.click(within(drawer).getByRole("button", { name: "Apply hold" }));
    return drawer;
  }

  it("a message for a member the drawer has no field for is listed by the banner", async () => {
    open({ hold_type: NO_FIELD });
    const drawer = await send();

    const banner = await within(drawer).findByRole("alert");
    expect(within(banner).getByRole("heading", { name: TITLE })).toBeTruthy();
    expect(within(banner).getByText(NO_FIELD)).toBeTruthy();
  });

  it("a message for the reason stands at the field and the banner does not repeat it", async () => {
    open({ reason: AT_REASON, obligation_key: NO_FIELD });
    const drawer = await send();

    const reason = within(drawer).getByLabelText(/^Reason/);
    await waitFor(() => {
      expect(describedBy(reason)).toContain(AT_REASON);
    });
    const banner = within(drawer).getByRole("alert");
    expect(within(banner).queryByText(AT_REASON)).toBeNull();
    // At contract level no obligation is on screen: the message of that member is the banner's.
    expect(within(banner).getByText(NO_FIELD)).toBeTruthy();
  });

  it("after a 412 the banner says that the record changed, in place of the problem", async () => {
    open({}, 412);
    const drawer = await send();

    expect(await within(drawer).findByRole("heading", { name: RECORD_CHANGED })).toBeTruthy();
    expect(within(drawer).queryByRole("heading", { name: TITLE })).toBeNull();
  });
});

describe("SF-03 Edit memos under a refused command", () => {
  const NO_FIELD = "Use a key of at most 40 characters.";
  const AT_COMMENT = "Say what changed and why.";

  function open(messages: Readonly<Record<string, string>>, status = 422) {
    server.use(
      http.get(apiUrl("/api/v1/dimensions"), () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.post(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/update-memos`), () =>
        refusedWith(messages, { status }),
      ),
    );
    renderWithApp(
      <EditMemosDrawer contract={CONTRACT} obligations={[O1]} onClose={() => undefined} />,
    );
  }

  async function send(): Promise<HTMLElement> {
    const drawer = await screen.findByRole("dialog", { name: "Edit memos" });
    fireEvent.change(within(drawer).getByLabelText(/^Comment/), {
      target: { value: "Region added for the segment report." },
    });
    fireEvent.click(within(drawer).getByRole("button", { name: "Save memos" }));
    return drawer;
  }

  it("a message for an attribute, which no field shows, is listed by the banner", async () => {
    // An attribute may be named as a field of the drawer is: the pointer's first member decides.
    open({ "custom_attributes.comment": NO_FIELD });
    const drawer = await send();

    const banner = await within(drawer).findByRole("alert");
    expect(within(banner).getByRole("heading", { name: TITLE })).toBeTruthy();
    expect(within(banner).getByText(NO_FIELD)).toBeTruthy();
    expect(describedBy(within(drawer).getByLabelText(/^Comment/))).not.toContain(NO_FIELD);
  });

  it("a message for the comment and one for a memo stand at their fields, not in the banner", async () => {
    open({ comment: AT_COMMENT, memo_2: "Use at most 400 characters." });
    const drawer = await send();

    const comment = within(drawer).getByLabelText(/^Comment/);
    await waitFor(() => {
      expect(describedBy(comment)).toContain(AT_COMMENT);
    });
    expect(describedBy(within(drawer).getByLabelText(/^Memo 2/))).toContain(
      "Use at most 400 characters.",
    );
    const banner = within(drawer).getByRole("alert");
    expect(banner.textContent).toBe(TITLE + REFUSAL_REFERENCE);
  });

  it("after a 412 the banner says that the record changed, in place of the problem", async () => {
    open({}, 412);
    const drawer = await send();

    expect(await within(drawer).findByRole("heading", { name: RECORD_CHANGED })).toBeTruthy();
    expect(within(drawer).queryByRole("heading", { name: TITLE })).toBeNull();
  });
});

describe("SF-03 Combine with another contract under a refused command", () => {
  const OTHER_ID = "7e8f90a1-b2c3-4d4e-8f5a-6b7c8d9e0f1a";
  const GROUP_ID = "8f90a1b2-c3d4-4e5f-9a6b-7c8d9e0f1a2b";
  const IN_GROUP = "This contract is already in a group.";
  const NO_FIELD = "Contracts of two legal entities cannot be combined.";

  function open(create: () => Response, submit?: () => Response) {
    server.use(
      http.get(apiUrl("/api/v1/contracts"), () =>
        HttpResponse.json({
          items: [
            workbenchContract(),
            workbenchContract({ id: OTHER_ID, external_id: "SF-ORD-10003" }),
          ],
          next_cursor: null,
        }),
      ),
      http.get(apiUrl("/api/v1/currencies"), () =>
        HttpResponse.json({
          items: [
            { code: "USD", minor_unit: 2, name: "US Dollar", numeric_code: "840", is_active: true },
          ],
          next_cursor: null,
        }),
      ),
      http.post(apiUrl("/api/v1/combination-groups"), create),
      http.post(
        apiUrl(`/api/v1/combination-groups/${GROUP_ID}/submit`),
        submit ?? (() => HttpResponse.json({ id: GROUP_ID, approval_request_id: null })),
      ),
    );
    renderWithApp(<CombineDrawer contract={CONTRACT} onClose={() => undefined} />);
  }

  async function send(): Promise<HTMLElement> {
    const drawer = await screen.findByRole("dialog", { name: "Combine with another contract" });
    const contracts = within(drawer).getByRole("combobox", { name: /^Contracts/ });
    fireEvent.keyDown(contracts, { key: "ArrowDown" });
    fireEvent.mouseDown(await within(drawer).findByRole("option", { name: "SF-ORD-10003" }));
    fireEvent.click(within(drawer).getByRole("radio", { name: "(a) Negotiated as a package" }));
    fireEvent.change(within(drawer).getByLabelText(/^Rationale/), {
      target: { value: "Both orders were negotiated in one proposal." },
    });
    fireEvent.click(within(drawer).getByRole("button", { name: "Submit for approval" }));
    return drawer;
  }

  it("a message for a member the drawer has no field for is listed by the banner", async () => {
    open(() => refusedWith({ entity_id: NO_FIELD }));
    const drawer = await send();

    const banner = await within(drawer).findByRole("alert");
    expect(within(banner).getByText(NO_FIELD)).toBeTruthy();
  });

  it("a message for one contract of the list stands at the Contracts field, not in the banner", async () => {
    open(() => refusedWith({ "contract_ids.1": IN_GROUP, criterion: "Choose the criterion met." }));
    const drawer = await send();

    const contracts = within(drawer).getByRole("combobox", { name: /^Contracts/ });
    await waitFor(() => {
      expect(describedBy(contracts)).toContain(IN_GROUP);
    });
    expect(within(drawer).getByText("Choose the criterion met.")).toBeTruthy();
    const banner = within(drawer).getByRole("alert");
    expect(banner.textContent).toBe(TITLE + REFUSAL_REFERENCE);
  });

  it("the refusal of the group's submission, which names no field of the drawer, is said whole", async () => {
    open(
      () => HttpResponse.json({ id: GROUP_ID, approval_request_id: null }, { status: 201 }),
      () =>
        refusedWith(
          { status: NO_FIELD },
          { slug: "invalid-transition", status: 409, title: "This action is not available now" },
        ),
    );
    const drawer = await send();

    const banner = await within(drawer).findByRole("alert");
    expect(
      within(banner).getByRole("heading", { name: "This action is not available now" }),
    ).toBeTruthy();
    expect(within(banner).getByText(NO_FIELD)).toBeTruthy();
  });
});

describe("SF-03 Dismiss suggestion under a refused command", () => {
  const SUGGESTION = {
    id: "90a1b2c3-d4e5-4f6a-8b7c-8d9e0f1a2b3c",
    contract_external_ids: ["SF-ORD-10002", "SF-ORD-10003"],
  } as unknown as CombinationSuggestion;
  const NO_FIELD = "This suggestion was dismissed by another user.";
  const AT_RATIONALE = "Say why the contracts are not one arrangement.";

  async function send(messages: Readonly<Record<string, string>>): Promise<HTMLElement> {
    server.use(
      http.post(apiUrl(`/api/v1/combination-suggestions/${SUGGESTION.id}/dismiss`), () =>
        refusedWith(messages),
      ),
    );
    renderWithApp(<DismissSuggestionModal suggestion={SUGGESTION} onClose={() => undefined} />);
    const modal = await screen.findByRole("dialog", { name: "Dismiss suggestion" });
    fireEvent.change(within(modal).getByLabelText(/^Rationale/), {
      target: { value: "Negotiated a year apart by different teams." },
    });
    fireEvent.click(within(modal).getByRole("button", { name: "Dismiss suggestion" }));
    return modal;
  }

  it("a message for a member the form has no field for is listed by the banner", async () => {
    const modal = await send({ status: NO_FIELD });

    const banner = await within(modal).findByRole("alert");
    expect(within(banner).getByText(NO_FIELD)).toBeTruthy();
  });

  it("a message for the rationale stands at the field and the banner does not repeat it", async () => {
    const modal = await send({ rationale: AT_RATIONALE });

    const rationale = within(modal).getByLabelText(/^Rationale/);
    await waitFor(() => {
      expect(describedBy(rationale)).toContain(AT_RATIONALE);
    });
    expect(within(modal).getByRole("alert").textContent).toBe(TITLE + REFUSAL_REFERENCE);
  });
});

describe("SF-03 Record distinct review under a refused command", () => {
  const O2 = workbenchObligation({ obligation_key: "O2" }) as unknown as Obligation;
  const NO_FIELD = "A review of this obligation is waiting for its reviewer.";
  const AT_BASIS = "Cite a paragraph of ASC 606-10-25-19 to 25-22.";

  async function send(messages: Readonly<Record<string, string>>): Promise<HTMLElement> {
    server.use(
      http.post(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/obligations/O1/distinct-review`), () =>
        refusedWith(messages),
      ),
    );
    renderWithApp(
      <DistinctReviewDrawer
        contract={CONTRACT}
        obligation={O1}
        obligations={[O1, O2]}
        onClose={() => undefined}
      />,
    );
    const drawer = await screen.findByRole("dialog", { name: "Record distinct review" });
    fireEvent.click(within(drawer).getByRole("radio", { name: "Distinct" }));
    select(drawer, /^Basis/, "Separately identifiable (ASC 606-10-25-21)");
    fireEvent.change(within(drawer).getByLabelText(/^Rationale/), {
      target: { value: "The seats are sold and used without the implementation." },
    });
    fireEvent.click(within(drawer).getByRole("button", { name: "Save review" }));
    return drawer;
  }

  it("a message for a member that is not on screen is listed by the banner", async () => {
    // "Combine with" is asked of an obligation that is not distinct only.
    const drawer = await send({ integrates_into_obligation_key: NO_FIELD });

    const banner = await within(drawer).findByRole("alert");
    expect(within(banner).getByText(NO_FIELD)).toBeTruthy();
  });

  it("a message for one cited paragraph stands at the Basis field, not in the banner", async () => {
    const drawer = await send({ "codification_refs.0": AT_BASIS });

    const basis = within(drawer).getByRole("combobox", { name: /^Basis/ });
    await waitFor(() => {
      expect(describedBy(basis)).toContain(AT_BASIS);
    });
    expect(within(drawer).getByRole("alert").textContent).toBe(TITLE + REFUSAL_REFERENCE);
  });
});

describe("SF-03 Record delivery under a refused command", () => {
  const EXCEEDS = "The quantity delivered exceeds the quantity that remains.";
  const NO_FIELD = "Events of this obligation are on hold.";
  const DETAIL = "2 fields need attention.";
  const NO_PREVIEW = "The preview is not available";
  const AT_PREVIEW = "The period of this date is closed.";

  async function fill(
    submission: Readonly<Record<string, string>>,
    preview: Readonly<Record<string, string>>,
  ): Promise<HTMLElement> {
    server.use(
      http.post(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/events/preview`), () =>
        refusedWith(preview, { title: NO_PREVIEW }),
      ),
      http.post(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/events`), () =>
        refusedWith(submission, { detail: DETAIL }),
      ),
    );
    renderWithApp(
      <RecordEventDrawer
        contract={CONTRACT}
        obligations={[O1]}
        kind="delivery"
        obligationKey="O1"
        onClose={() => undefined}
      />,
    );
    const drawer = await screen.findByRole("dialog", { name: "Record delivery" });
    fireEvent.change(within(drawer).getByLabelText(/^Quantity/), { target: { value: "120" } });
    select(drawer, /^Trigger/, "Delivery");
    const date = within(drawer).getByRole("textbox", { name: /^Effective date/ });
    fireEvent.change(date, { target: { value: "30 Sep 2026" } });
    fireEvent.blur(date);
    return drawer;
  }

  it("a message stands at its field once, and the banner says the detail, what no field shows and the reference", async () => {
    // The obligation of the pane is read only here: a message of its member is the banner's.
    const drawer = await fill(
      { "events.0.payload.quantity": EXCEEDS, "events.0.obligation_key": NO_FIELD },
      {},
    );
    fireEvent.click(within(drawer).getByRole("button", { name: "Submit for approval" }));

    const quantity = within(drawer).getByLabelText(/^Quantity/);
    await waitFor(() => {
      expect(describedBy(quantity)).toContain(EXCEEDS);
    });
    const banner = within(drawer).getByRole("heading", { name: TITLE }).closest('[role="alert"]');
    expect(banner?.textContent).toBe(TITLE + DETAIL + NO_FIELD + REFUSAL_REFERENCE);
  });

  it("a refused preview says every sentence of its refusal: it has no field of its own", async () => {
    const drawer = await fill({}, { "events.0.effective_date": AT_PREVIEW });

    const heading = await within(drawer).findByRole(
      "heading",
      { name: NO_PREVIEW },
      { timeout: 3000 },
    );
    expect(heading.closest('[role="alert"]')?.textContent).toBe(
      NO_PREVIEW + AT_PREVIEW + REFUSAL_REFERENCE,
    );
  });
});

describe("SF-03 Documents under a refused upload", () => {
  it("the drawer has no field for a message, so the banner says every sentence", async () => {
    const sentence = "A file of this content is already attached to the contract.";
    server.use(
      http.get(apiUrl("/api/v1/attachments"), () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.post(apiUrl("/api/v1/files"), () =>
        HttpResponse.json(
          {
            id: "a1b2c3d4-0000-4000-8000-0000000000f1",
            purpose: "ATTACHMENT",
            media_type: "application/pdf",
            original_filename: "order-form.pdf",
            size_bytes: 4,
            sha256: "c".repeat(64),
            legal_hold: false,
            retention_until: null,
            shredded_at: null,
            created_at: "2026-09-13T09:00:00Z",
            created_by: null,
            created_by_kind: "USER",
          },
          { status: 201 },
        ),
      ),
      http.post(apiUrl("/api/v1/attachments"), () => refusedWith({ file_object_id: sentence })),
    );
    renderWithApp(<DocumentsDrawer contract={CONTRACT} canUpload onClose={() => undefined} />);
    const drawer = await screen.findByRole("dialog", { name: "Documents" });
    const form = new File(["form"], "order-form.pdf", { type: "application/pdf", lastModified: 1 });
    fireEvent.change(within(drawer).getByLabelText("Upload document"), {
      target: { files: [form] },
    });

    const banner = await within(drawer).findByRole("alert");
    expect(banner.textContent).toBe(TITLE + sentence + REFUSAL_REFERENCE);
  });
});

describe("SF-03 Void this event under a refused request", () => {
  it("the modal shows no message at a field, so the banner says every sentence", async () => {
    const EVENT_ID = "b1c2d3e4-0000-4000-8000-0000000000e1";
    const sentence = "A void of this event is already waiting for approval.";
    server.use(
      http.post(apiUrl(`/api/v1/events/${EVENT_ID}/request-void`), () =>
        refusedWith({ reason_code: sentence }),
      ),
    );
    renderWithApp(
      <VoidEventModal
        event={{ id: EVENT_ID } as unknown as ObligationEvent}
        onClose={() => undefined}
        onDone={() => undefined}
      />,
    );
    const modal = await screen.findByRole("alertdialog", { name: "Void this event?" });
    select(modal, /^Reason code/, "Duplicate");
    fireEvent.change(within(modal).getByLabelText(/^Reason/, { selector: "textarea" }), {
      target: { value: "Recorded twice from the same delivery note." },
    });
    fireEvent.click(within(modal).getByRole("button", { name: "Void event" }));

    const banner = await within(modal).findByRole("alert");
    expect(banner.textContent).toBe(TITLE + sentence + REFUSAL_REFERENCE);
  });
});
