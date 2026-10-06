// @vitest-environment jsdom
// SF-03 Release hold (SCREENS §4.9.4 rev 1.75; lane SECFIX-ACT's item HOLD-RELEASE-READ-1 on the screens;
// 04 §16.1 `POST /contracts/{id}/release-hold`, §16.1 and §16.2 rev 1.299 `holds`, T-CON-20). The drawer
// lists every open hold — the contract's own, then each obligation's — offers the ones the API says are
// released by hand, shows the API's sentence for the others, and sends the chosen hold's id with a
// comment under the contract's head. Until 04 rev 1.299 no read answered that id: a hold applied on a
// screen had no exit on the screens. The members and the refusals are as measured through the API.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";

import type { Contract } from "../../../lib/api/queries/contracts";
import type { Hold, Obligation } from "../../../lib/api/queries/obligations";
import { hasMessage, t } from "../../../lib/i18n/t";
import { renderWithApp } from "../../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";
import {
  describedBy,
  RECORD_CHANGED,
  REFUSAL_REFERENCE,
  refusedWith,
} from "../../../test/refusals";
import {
  CONTRACT_ID,
  K02,
  MAYA_USER,
  SYSTEM_ACTOR,
  workbenchContract,
  workbenchObligation,
} from "../../../test/workbench";
import { ReleaseHoldDrawer } from "./holds";

installMswServer();

afterEach(() => {
  cleanup();
});

const WHOLE_ID = "01a0ff4f-d9d6-7ee3-9a26-9a68a456e700";
const O2_HOLD_ID = "01a0ff4f-dcc5-7ec3-8809-9afb8d18ad6f";
const RECORD_HOLD_ID = "01a0ff4f-ec2b-7aa2-a8f4-48187244bf43";
const COMMENT = "Dispute settled with the customer.";
const BY_REVIEW = "This hold is released by the review of judgement record JDG-000001.";

/** A hold of the whole contract that a person applied, as API-S-Contract lists it. */
const WHOLE: Hold = {
  id: WHOLE_ID,
  level: "contract",
  hold_type: "journal_export",
  hold_source: "MANUAL",
  reason: "Invoice dispute pending with the customer.",
  applied_by: MAYA_USER,
  applied_at: "2026-09-12T12:00:00Z",
  release_refusal: null,
};
/** The hold of one obligation, as that obligation lists it. */
const OF_O2: Hold = {
  ...WHOLE,
  id: O2_HOLD_ID,
  level: "obligation",
  hold_type: "recognition",
  reason: "Customer disputes O2.",
  applied_at: "2026-09-13T08:30:00Z",
};
/** The hold of a judgement record that waits for its review: not released by hand. */
const OF_RECORD: Hold = {
  id: RECORD_HOLD_ID,
  level: "contract",
  hold_type: "recognition",
  hold_source: "SYSTEM",
  reason: "Judgement record JDG-000001 (COLLECTIBILITY) is not reviewed.",
  applied_by: SYSTEM_ACTOR,
  applied_at: "2026-09-14T09:00:00Z",
  release_refusal: BY_REVIEW,
};
const WHOLE_LABEL =
  "Journal export hold · Invoice dispute pending with the customer. · applied 12 Sep 2026 12:00 UTC";
const O2_LABEL = "O2 · Recognition hold · Customer disputes O2. · applied 13 Sep 2026 08:30 UTC";
const RECORD_LABEL =
  "Recognition hold · Judgement record JDG-000001 (COLLECTIBILITY) is not reviewed. · applied 14 Sep 2026 09:00 UTC";

function contract(holds: readonly Hold[]): Contract {
  return workbenchContract({ on_hold: true, holds }) as unknown as Contract;
}

function obligation(key: string, holds: readonly Hold[]): Obligation {
  return workbenchObligation({ obligation_key: key, holds }) as unknown as Obligation;
}

interface Sent {
  readonly body: unknown;
  readonly ifMatch: string | null;
}

/** The release route with what it was sent; `refuse` answers in the route's place. */
function route(refuse: () => Response | null = () => null): Sent[] {
  const sent: Sent[] = [];
  server.use(
    http.post(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/release-hold`), async ({ request }) => {
      sent.push({ body: await request.json(), ifMatch: request.headers.get("If-Match") });
      return refuse() ?? HttpResponse.json(workbenchContract({ on_hold: false, holds: [] }));
    }),
  );
  return sent;
}

interface Opened {
  readonly drawer: HTMLElement;
  readonly closed: () => boolean;
}

async function open(
  holds: readonly Hold[],
  obligations: readonly Obligation[],
  holdId?: string,
): Promise<Opened> {
  let closed = false;
  renderWithApp(
    <ReleaseHoldDrawer
      contract={contract(holds)}
      obligations={obligations}
      holdId={holdId}
      onClose={() => {
        closed = true;
      }}
    />,
  );
  return {
    drawer: await screen.findByRole("dialog", { name: "Release hold" }),
    closed: () => closed,
  };
}

/** The select "Hold" with its list open: the options' words. */
function options(drawer: HTMLElement): (string | null)[] {
  const trigger = within(drawer).getByRole("combobox", { name: /^Hold/ });
  fireEvent.click(trigger);
  const list = document.getElementById(trigger.getAttribute("aria-controls") ?? "");
  if (list === null) {
    throw new Error("The select Hold has no open list");
  }
  return within(list)
    .getAllByRole("option")
    .map((item) => item.textContent);
}

function pick(drawer: HTMLElement, option: string): void {
  const trigger = within(drawer).getByRole("combobox", { name: /^Hold/ });
  if (trigger.getAttribute("aria-expanded") !== "true") {
    fireEvent.click(trigger);
  }
  const list = document.getElementById(trigger.getAttribute("aria-controls") ?? "");
  if (list === null) {
    throw new Error("The select Hold has no open list");
  }
  fireEvent.mouseDown(within(list).getByRole("option", { name: option }));
}

function comment(drawer: HTMLElement, text: string): void {
  fireEvent.change(within(drawer).getByLabelText(/^Comment/), { target: { value: text } });
}

function press(drawer: HTMLElement): void {
  fireEvent.click(within(drawer).getByRole("button", { name: "Release hold" }));
}

interface OpenApi {
  readonly components: {
    readonly schemas: Readonly<Record<string, { readonly enum?: readonly string[] }>>;
  };
}

/** The literals of an enumeration in the order the API document lists them. */
function apiEnum(name: string): readonly string[] {
  const here = dirname(fileURLToPath(import.meta.url));
  const file = resolve(here, "../../../../../docs/api/openapi.json");
  const document = JSON.parse(readFileSync(file, "utf8")) as OpenApi;
  return document.components.schemas[name]?.enum ?? [];
}

describe("the words of a hold", () => {
  it("every hold type and every hold source the API document states has its words", () => {
    // The pane's table and the drawer's options read both through a catalogue key without a
    // fallback: `t()` throws on a key the catalogue lacks, and a production build prints the key.
    const types = apiEnum("HoldType");
    const sources = apiEnum("HoldSource");
    expect(types.filter((value) => !hasMessage(`contracts.history.hold.${value}`))).toEqual([]);
    expect(
      sources.filter((value) => !hasMessage(`contracts.obligation.holds.source.${value}`)),
    ).toEqual([]);
    expect(types.map((value) => [value, t(`contracts.history.hold.${value}`)])).toEqual([
      ["recognition", "Recognition hold"],
      ["journal_export", "Journal export hold"],
    ]);
    // SCREENS §5.6: "System", "Rule", "Manual".
    expect(
      sources.map((value) => [value, t(`contracts.obligation.holds.source.${value}`)]),
    ).toEqual([
      ["SYSTEM", "System"],
      ["USER_RULE", "Rule"],
      ["MANUAL", "Manual"],
    ]);
  });
});

describe("SF-03 Release hold", () => {
  it("lists the open holds of the contract and of its obligations, the contract's first, and sends the chosen hold's id with the comment under the contract's head", async () => {
    const sent = route();
    const { drawer, closed } = await open(
      [WHOLE],
      [obligation("O1", []), obligation("O2", [OF_O2])],
    );

    // An obligation's hold carries its key; the instant is the API's, in UTC.
    expect(options(drawer)).toEqual([WHOLE_LABEL, O2_LABEL]);
    pick(drawer, O2_LABEL);
    comment(drawer, `  ${COMMENT} `);
    press(drawer);

    expect(await screen.findByText(`Hold released on ${K02}.`)).toBeTruthy();
    expect(sent).toEqual([{ body: { hold_id: O2_HOLD_ID, comment: COMMENT }, ifMatch: '"s5"' }]);
    expect(closed()).toBe(true);
  });

  it("one hold alone is chosen at once, and the hold the pane named is chosen when the drawer opens", async () => {
    const sent = route();
    const alone = await open([WHOLE], [obligation("O1", [])]);
    expect(within(alone.drawer).getByRole("combobox", { name: /^Hold/ }).textContent).toBe(
      WHOLE_LABEL,
    );
    comment(alone.drawer, COMMENT);
    press(alone.drawer);
    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0]?.body).toEqual({ hold_id: WHOLE_ID, comment: COMMENT });
    cleanup();

    // Two holds: none is chosen for the member, but the one the pane named.
    const named = await open([WHOLE], [obligation("O2", [OF_O2])], O2_HOLD_ID);
    expect(within(named.drawer).getByRole("combobox", { name: /^Hold/ }).textContent).toBe(
      O2_LABEL,
    );
    comment(named.drawer, COMMENT);
    press(named.drawer);
    await waitFor(() => expect(sent).toHaveLength(2));
    expect(sent[1]?.body).toEqual({ hold_id: O2_HOLD_ID, comment: COMMENT });
  });

  it("a hold that is not released by hand is no option: it stands under the select with the API's sentence", async () => {
    route();
    const { drawer } = await open([WHOLE, OF_RECORD], [obligation("O2", [OF_O2])]);

    expect(options(drawer)).toEqual([WHOLE_LABEL, O2_LABEL]);
    const kept = within(drawer).getByRole("list", { name: "Not released by hand" });
    expect(
      within(kept)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual([`${RECORD_LABEL}${BY_REVIEW}`]);
  });

  it("where no hold is released by hand the drawer says why for each and has nothing to send", async () => {
    const sent = route();
    const closedContract = "A voided or terminated contract takes no hold.";
    const { drawer } = await open(
      [{ ...WHOLE, release_refusal: closedContract }],
      [obligation("O2", [{ ...OF_O2, release_refusal: closedContract }])],
    );

    const kept = within(drawer).getByRole("list", { name: "Not released by hand" });
    expect(
      within(kept)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual([`${WHOLE_LABEL}${closedContract}`, `${O2_LABEL}${closedContract}`]);
    expect(within(drawer).queryByRole("combobox")).toBeNull();
    expect(within(drawer).queryByLabelText(/^Comment/)).toBeNull();
    expect(within(drawer).queryByRole("button", { name: "Release hold" })).toBeNull();
    expect(sent).toEqual([]);
  });

  it("without a hold chosen, or with a comment under ten characters, nothing is sent and each field says so", async () => {
    const sent = route();
    const { drawer, closed } = await open([WHOLE], [obligation("O2", [OF_O2])]);
    comment(drawer, "Settled.");
    press(drawer);

    const hold = within(drawer).getByRole("combobox", { name: /^Hold/ });
    await waitFor(() => {
      expect(describedBy(hold)).toContain("Choose a value.");
    });
    const field = within(drawer).getByLabelText(/^Comment/);
    expect(describedBy(field)).toContain("Enter at least 10 characters.");
    expect(sent).toEqual([]);

    // Each of the two holds the release back by itself. A full comment without a hold chosen: the
    // pause gives a request that must not be sent the time to be sent.
    comment(drawer, COMMENT);
    press(drawer);
    await waitFor(() => {
      expect(describedBy(field)).not.toContain("Enter at least 10 characters.");
    });
    expect(describedBy(hold)).toContain("Choose a value.");
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(sent).toEqual([]);

    // A hold chosen with a short comment.
    pick(drawer, WHOLE_LABEL);
    await waitFor(() => {
      expect(describedBy(hold)).not.toContain("Choose a value.");
    });
    comment(drawer, "Settled.");
    press(drawer);
    await waitFor(() => {
      expect(describedBy(field)).toContain("Enter at least 10 characters.");
    });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(sent).toEqual([]);
    expect(closed()).toBe(false);
  });

  it("a hold that is released while the drawer is open is no choice any more", async () => {
    const sent = route();
    function Harness() {
      const [holds, setHolds] = useState<readonly Hold[]>([OF_O2]);
      return (
        <>
          <button type="button" onClick={() => setHolds([])}>
            O2 released elsewhere
          </button>
          <ReleaseHoldDrawer
            contract={contract([
              WHOLE,
              { ...WHOLE, id: RECORD_HOLD_ID, reason: "A second dispute." },
            ])}
            obligations={[obligation("O2", holds)]}
            holdId={O2_HOLD_ID}
            onClose={() => undefined}
          />
        </>
      );
    }
    renderWithApp(<Harness />);
    const drawer = await screen.findByRole("dialog", { name: "Release hold" });
    const hold = within(drawer).getByRole("combobox", { name: /^Hold/ });
    expect(hold.textContent).toBe(O2_LABEL);

    // The button stands outside the modal drawer: it is pressed as the read's answer would arrive.
    fireEvent.click(screen.getByRole("button", { name: "O2 released elsewhere", hidden: true }));
    await waitFor(() => expect(hold.textContent).not.toBe(O2_LABEL));
    comment(drawer, COMMENT);
    press(drawer);
    await waitFor(() => {
      expect(describedBy(hold)).toContain("Choose a value.");
    });
    expect(sent).toEqual([]);
  });

  it("a refused release is shown as the API says it: its sentence in the banner, a message of the comment at the field, and a changed record in the banner's own line", async () => {
    // The bodies are the route's, measured on the API (register index 281).
    const released = "This hold is already released.";
    const AT_HOLD = "Choose a hold of this contract.";
    const refusals: Response[] = [
      problemResponse("invalid-transition", 409, "Action not available in this state", {
        code: null,
        detail: released,
        errors: [{ field: "status", message: released, row: null, rule_id: "DB-03", sheet: null }],
      }),
      problemResponse("not-found", 404, "Not found", {
        code: null,
        detail: "The contract has no hold with this id.",
      }),
      problemResponse("validation-failed", 422, "Check the highlighted fields", {
        code: null,
        detail: "1 field needs attention.",
        errors: [
          {
            field: "comment",
            message: "String should have at least 10 characters",
            row: null,
            rule_id: null,
            sheet: null,
          },
        ],
      }),
      // Not the route's own: a message for the member the select sends, placed as DG-FE-06 asks.
      refusedWith({ hold_id: AT_HOLD }),
      problemResponse("precondition-failed", 412, "Record changed", {
        code: null,
        detail:
          "This record changed since you opened it. Reload to see the latest version, then try again.",
      }),
    ];
    let turn = 0;
    const sent = route(() => refusals[turn++] ?? null);
    const { drawer, closed } = await open([WHOLE], [obligation("O1", [])]);
    comment(drawer, COMMENT);

    press(drawer);
    const banner = await within(drawer).findByRole("alert");
    await waitFor(() =>
      expect(banner.textContent).toBe(
        `Action not available in this state${released}${REFUSAL_REFERENCE}`,
      ),
    );

    press(drawer);
    await waitFor(() =>
      expect(within(drawer).getByRole("alert").textContent).toBe(
        `Not foundThe contract has no hold with this id.${REFUSAL_REFERENCE}`,
      ),
    );

    press(drawer);
    const field = within(drawer).getByLabelText(/^Comment/);
    await waitFor(() => {
      expect(describedBy(field)).toContain("String should have at least 10 characters");
    });

    press(drawer);
    const hold = within(drawer).getByRole("combobox", { name: /^Hold/ });
    await waitFor(() => {
      expect(describedBy(hold)).toContain(AT_HOLD);
    });
    expect(within(drawer).getByRole("alert").textContent).toBe(
      `Check the highlighted fields${REFUSAL_REFERENCE}`,
    );

    press(drawer);
    expect(await within(drawer).findByRole("heading", { name: RECORD_CHANGED })).toBeTruthy();
    expect(sent).toHaveLength(5);
    expect(closed()).toBe(false);
    expect(screen.queryByText(`Hold released on ${K02}.`)).toBeNull();
  });
});
