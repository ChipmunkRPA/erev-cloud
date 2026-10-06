// @vitest-environment jsdom
// SF-03 Combine with another contract: the proposal the drawer made and did not submit (SCREENS §4.9.7
// rev 1.78; lane F-RPS-REG's item COMBINATION-PROPOSAL-DISCARD-1 on the screens; 04 T-CON-19 "The
// `COMBINATION` topic" rev 1.289, `POST /combination-groups/{id}/discard`). One press sends the group
// and then its submission. A refused submission left the group proposed: a press with a changed form
// made a second group beside it, closing the drawer left it, and no screen lists a proposed group.
// The drawer gives up its proposal before it proposes another form, and when it closes. The stand-in
// answers as measured through the routes (register index 266).
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import type { Contract } from "../../../lib/api/queries/contracts";
import { renderWithApp } from "../../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";
import { describedBy, REFUSAL_REFERENCE, refusedWith } from "../../../test/refusals";
import { workbenchContract } from "../../../test/workbench";
import { CombineDrawer } from "./combine";

installMswServer();

afterEach(() => {
  cleanup();
});

const CONTRACT = workbenchContract() as unknown as Contract;
const OTHER_ID = "7e8f90a1-b2c3-4d4e-8f5a-6b7c8d9e0f1a";
const RATIONALE = "Both orders were negotiated in one proposal.";
const LATER = "Both orders were negotiated in one proposal, in May.";
const NOT_SUBMITTED = "The combination was not submitted. Its proposal was discarded.";
const SUBMITTED = "Combination submitted.";
const NO_ANSWER = "No answer came back from the server. Try again.";
// The API's words, as measured: the title of a refused transition and the two refusals of a discard.
const UNAVAILABLE = "Action not available in this state";
const WAITS = "This combination waits for approval. Withdraw its request, or have it rejected.";
const NOT_DISCARDABLE = "Only a proposed combination that is not submitted can be discarded.";
const ALREADY_COMBINED = "The contract already belongs to a combination group.";

/**
 * A submission the API refuses after it took the first step, as measured: a contract of the proposal
 * was combined elsewhere since (422 on `contract_ids.0`, the sentence as the detail too).
 */
function notSubmitted(): Response {
  return refusedWith({ "contract_ids.0": ALREADY_COMBINED }, { detail: ALREADY_COMBINED });
}

/** A discard the API refuses: 409 `invalid-transition` on `status`, with its sentence. */
function notDiscarded(sentence: string): () => Response {
  return () =>
    problemResponse("invalid-transition", 409, UNAVAILABLE, {
      code: null,
      detail: sentence,
      errors: [{ field: "status", message: sentence, row: null, rule_id: "DB-03", sheet: null }],
    });
}

interface Sent {
  readonly call: string;
  readonly key: string | null;
  readonly body: unknown;
}

interface World {
  /** Every command the drawer sent, in order. */
  readonly sent: Sent[];
  /** What the next submissions answer, first to last; a submission behind them is accepted. */
  submissions: (() => Response)[];
  /** What the next discards answer, first to last; a discard behind them is taken. */
  discards: (() => Response)[];
  /** How often the drawer closed. */
  closed: number;
}

function serve(): World {
  const world: World = { sent: [], submissions: [], discards: [], closed: 0 };
  // The API keeps the answer of a step under its Idempotency-Key and replays it for that key — also
  // once the group is discarded (measured): one group a key.
  const groups = new Map<string, string>();
  const log = async (request: Request, call: string): Promise<void> => {
    const text = await request.text();
    world.sent.push({
      call,
      key: request.headers.get("Idempotency-Key"),
      body: text === "" ? null : (JSON.parse(text) as unknown),
    });
  };
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
    http.post(apiUrl("/api/v1/combination-groups"), async ({ request }) => {
      await log(request, "POST /combination-groups");
      const key = request.headers.get("Idempotency-Key") ?? "";
      const id = groups.get(key) ?? `group-${String(groups.size + 1)}`;
      groups.set(key, id);
      return HttpResponse.json({ id, approval_request_id: null }, { status: 201 });
    }),
    http.post(apiUrl("/api/v1/combination-groups/:groupId/submit"), async ({ request, params }) => {
      await log(request, `POST /combination-groups/${String(params.groupId)}/submit`);
      const refuse = world.submissions.shift();
      return refuse === undefined
        ? HttpResponse.json({ id: params.groupId, approval_request_id: null })
        : refuse();
    }),
    http.post(
      apiUrl("/api/v1/combination-groups/:groupId/discard"),
      async ({ request, params }) => {
        await log(request, `POST /combination-groups/${String(params.groupId)}/discard`);
        const refuse = world.discards.shift();
        return refuse === undefined
          ? HttpResponse.json({ id: params.groupId, approval_request_id: null })
          : refuse();
      },
    ),
  );
  renderWithApp(
    <CombineDrawer
      contract={CONTRACT}
      onClose={() => {
        world.closed += 1;
      }}
    />,
  );
  return world;
}

function write(drawer: HTMLElement, text: string): void {
  fireEvent.change(within(drawer).getByLabelText(/^Rationale/), { target: { value: text } });
}

/** The drawer with SF-ORD-10003, criterion (a) and the rationale. */
async function filled(): Promise<HTMLElement> {
  const drawer = await screen.findByRole("dialog", { name: "Combine with another contract" });
  const contracts = within(drawer).getByRole("combobox", { name: /^Contracts/ });
  fireEvent.keyDown(contracts, { key: "ArrowDown" });
  fireEvent.mouseDown(await within(drawer).findByRole("option", { name: "SF-ORD-10003" }));
  fireEvent.click(within(drawer).getByRole("radio", { name: "(a) Negotiated as a package" }));
  write(drawer, RATIONALE);
  return drawer;
}

function submit(drawer: HTMLElement): HTMLElement {
  return within(drawer).getByRole("button", { name: "Submit for approval" });
}

/** Presses "Submit for approval" and waits until `count` commands were sent and the press is over. */
async function press(drawer: HTMLElement, world: World, count: number): Promise<void> {
  fireEvent.click(submit(drawer));
  await waitFor(() => expect(world.sent).toHaveLength(count));
  await waitFor(() => expect(submit(drawer).getAttribute("aria-busy")).toBeNull());
}

/** "Cancel", then the kit's question for a form that holds input. */
async function cancel(drawer: HTMLElement): Promise<void> {
  fireEvent.click(within(drawer).getByRole("button", { name: "Cancel" }));
  const question = await screen.findByRole("alertdialog", { name: "Discard changes?" });
  fireEvent.click(within(question).getByRole("button", { name: "Discard changes" }));
}

function calls(world: World): string[] {
  return world.sent.map((item) => item.call);
}

/** The time a request that must not be sent would take to be sent. */
function pause(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 50));
}

describe("SF-03 Combine with another contract: the proposal the drawer made", () => {
  it("a refused submission leaves the proposal with the drawer: an unchanged press sends the first step under the key it had and the submission again, and discards nothing", async () => {
    const world = serve();
    world.submissions = [notSubmitted, notSubmitted];
    const drawer = await filled();

    await press(drawer, world, 2);
    // The refusal names a member the first step sent: its sentence stands at that field.
    expect(describedBy(within(drawer).getByRole("combobox", { name: /^Contracts/ }))).toContain(
      ALREADY_COMBINED,
    );
    await press(drawer, world, 4);
    expect(calls(world)).toEqual([
      "POST /combination-groups",
      "POST /combination-groups/group-1/submit",
      "POST /combination-groups",
      "POST /combination-groups/group-1/submit",
    ]);
    expect(world.sent[0]?.key).not.toBeNull();
    expect(world.sent[2]?.key).toBe(world.sent[0]?.key);

    // Accepted at the third press: the combination is submitted, and nothing was given up.
    fireEvent.click(submit(drawer));
    expect(await screen.findByText(SUBMITTED)).toBeTruthy();
    await waitFor(() => expect(world.closed).toBe(1));
    expect(calls(world).slice(4)).toEqual([
      "POST /combination-groups",
      "POST /combination-groups/group-1/submit",
    ]);
    expect(screen.queryByText(NOT_SUBMITTED)).toBeNull();
  });

  it("a press with a changed form first gives up the proposal the drawer made, under a key of its own and without a body, and then proposes anew", async () => {
    const world = serve();
    world.submissions = [notSubmitted, notSubmitted, notSubmitted];
    const drawer = await filled();
    await press(drawer, world, 2);

    write(drawer, LATER);
    await press(drawer, world, 5);
    expect(calls(world).slice(2)).toEqual([
      "POST /combination-groups/group-1/discard",
      "POST /combination-groups",
      "POST /combination-groups/group-2/submit",
    ]);
    const [first, , discard, second] = world.sent;
    expect(discard?.body).toBeNull();
    expect(discard?.key).not.toBeNull();
    expect(new Set([first?.key, discard?.key, second?.key]).size).toBe(3);
    expect(second?.body).toEqual({
      contract_ids: [CONTRACT.id, OTHER_ID],
      criterion: "606-10-25-9(a)",
      rationale: LATER,
    });

    // Back to the first form: the second proposal is given up, and the first step goes out under a
    // key it never had — the key of the first press would replay the group that was discarded.
    write(drawer, RATIONALE);
    await press(drawer, world, 8);
    expect(calls(world).slice(5)).toEqual([
      "POST /combination-groups/group-2/discard",
      "POST /combination-groups",
      "POST /combination-groups/group-3/submit",
    ]);
    expect(world.sent[6]?.key).not.toBe(first?.key);
    expect(world.sent[6]?.body).toEqual(first?.body);
    expect(world.closed).toBe(0);
  });

  it("closing after a refused submission gives up the proposal without a question of its own, says so and closes", async () => {
    // "Cancel", the close button and Esc: the kit asks its one question of a form that holds input.
    for (const leave of ["Cancel", "Close", "Escape"]) {
      const world = serve();
      world.submissions = [notSubmitted];
      const drawer = await filled();
      await press(drawer, world, 2);

      if (leave === "Escape") {
        fireEvent.keyDown(drawer, { key: "Escape" });
      } else {
        fireEvent.click(within(drawer).getByRole("button", { name: leave }));
      }
      const question = await screen.findByRole("alertdialog", { name: "Discard changes?" });
      fireEvent.click(within(question).getByRole("button", { name: "Discard changes" }));

      // A neutral toast: nothing was achieved and nothing went wrong.
      const said = await screen.findByText(NOT_SUBMITTED);
      expect(said.closest("[data-tone]")?.getAttribute("data-tone")).toBe("neutral");
      await waitFor(() => expect(world.closed).toBe(1));
      expect(calls(world).slice(2)).toEqual(["POST /combination-groups/group-1/discard"]);
      expect(world.sent[2]?.body).toBeNull();
      expect(screen.queryAllByRole("alertdialog")).toEqual([]);
      cleanup();
      server.resetHandlers();
    }
  });

  it("a refused discard is shown as it comes: the drawer stays, and the next close asks nothing more of the API", async () => {
    const world = serve();
    world.submissions = [notSubmitted];
    world.discards = [notDiscarded(WAITS)];
    const drawer = await filled();
    await press(drawer, world, 2);

    await cancel(drawer);
    await waitFor(() =>
      expect(within(drawer).getByRole("alert").textContent).toBe(
        `${UNAVAILABLE}${WAITS}${REFUSAL_REFERENCE}`,
      ),
    );
    expect(world.closed).toBe(0);
    expect(screen.queryByText(NOT_SUBMITTED)).toBeNull();

    // The group is no proposal of the drawer any more: closing closes, and nothing is said.
    await waitFor(() => expect(submit(drawer).getAttribute("aria-busy")).toBeNull());
    await cancel(drawer);
    await waitFor(() => expect(world.closed).toBe(1));
    expect(calls(world).slice(2)).toEqual(["POST /combination-groups/group-1/discard"]);
    expect(screen.queryByText(NOT_SUBMITTED)).toBeNull();
  });

  it("a changed press whose discard is refused proposes nothing, and the next press proposes anew under a new key", async () => {
    const world = serve();
    world.submissions = [notSubmitted];
    world.discards = [notDiscarded(NOT_DISCARDABLE)];
    const drawer = await filled();
    await press(drawer, world, 2);

    write(drawer, LATER);
    await press(drawer, world, 3);
    expect(calls(world).slice(2)).toEqual(["POST /combination-groups/group-1/discard"]);
    expect(within(drawer).getByRole("alert").textContent).toBe(
      `${UNAVAILABLE}${NOT_DISCARDABLE}${REFUSAL_REFERENCE}`,
    );

    // The same form again: no proposal is the drawer's now, so nothing is given up first.
    fireEvent.click(submit(drawer));
    expect(await screen.findByText(SUBMITTED)).toBeTruthy();
    expect(calls(world).slice(3)).toEqual([
      "POST /combination-groups",
      "POST /combination-groups/group-2/submit",
    ]);
    expect(world.sent[3]?.key).not.toBe(world.sent[0]?.key);
  });

  it("a form that cannot be sent gives up nothing: the proposal stays until a press proposes another form or the drawer closes", async () => {
    const world = serve();
    world.submissions = [notSubmitted];
    const drawer = await filled();
    await press(drawer, world, 2);

    write(drawer, "Too short");
    fireEvent.click(submit(drawer));
    await pause();
    expect(world.sent).toHaveLength(2);

    await cancel(drawer);
    expect(await screen.findByText(NOT_SUBMITTED)).toBeTruthy();
    expect(calls(world).slice(2)).toEqual(["POST /combination-groups/group-1/discard"]);
  });

  it("a drawer that made no proposal closes without a discard, and so does one whose combination was submitted", async () => {
    // Nothing was sent: "Cancel" closes at once, without a question and without a word.
    const untouched = serve();
    const empty = await screen.findByRole("dialog", { name: "Combine with another contract" });
    fireEvent.click(within(empty).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(untouched.closed).toBe(1));
    expect(untouched.sent).toEqual([]);
    cleanup();
    server.resetHandlers();

    // The first step was refused: no group was made.
    const refused = serve();
    server.use(
      http.post(apiUrl("/api/v1/combination-groups"), () =>
        refusedWith({ "contract_ids.1": ALREADY_COMBINED }),
      ),
    );
    const first = await filled();
    fireEvent.click(submit(first));
    await within(first).findByRole("alert");
    await cancel(first);
    await waitFor(() => expect(refused.closed).toBe(1));
    expect(refused.sent).toEqual([]);
    expect(screen.queryByText(NOT_SUBMITTED)).toBeNull();
    cleanup();
    server.resetHandlers();

    // Submitted: the group waits for approval and is no proposal the drawer gives up.
    const sent = serve();
    const drawer = await filled();
    fireEvent.click(submit(drawer));
    expect(await screen.findByText(SUBMITTED)).toBeTruthy();
    await waitFor(() => expect(sent.closed).toBe(1));
    expect(calls(sent)).toEqual([
      "POST /combination-groups",
      "POST /combination-groups/group-1/submit",
    ]);
  });

  it("a discard that gets no answer keeps the drawer and its proposal: the next close sends it again under the same key", async () => {
    const world = serve();
    world.submissions = [notSubmitted];
    world.discards = [() => HttpResponse.error()];
    const drawer = await filled();
    await press(drawer, world, 2);

    await cancel(drawer);
    expect(await screen.findByText(NO_ANSWER)).toBeTruthy();
    expect(world.closed).toBe(0);
    expect(screen.queryByText(NOT_SUBMITTED)).toBeNull();

    await waitFor(() => expect(submit(drawer).getAttribute("aria-busy")).toBeNull());
    await cancel(drawer);
    expect(await screen.findByText(NOT_SUBMITTED)).toBeTruthy();
    await waitFor(() => expect(world.closed).toBe(1));
    expect(calls(world).slice(2)).toEqual([
      "POST /combination-groups/group-1/discard",
      "POST /combination-groups/group-1/discard",
    ]);
    expect(world.sent[3]?.key).toBe(world.sent[2]?.key);
  });
});
