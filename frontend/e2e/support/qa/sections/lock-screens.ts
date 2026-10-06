// Section P of the pass: where a lock request is decided. Row C-10 found the cockpit's "Lock period"
// unavailable to the Controller while the lock request is pending — the request itself is the pending
// approval the gate counts — so this section reads the other screen a decision can be given on: the
// request's own (SF-12:request). It uses the one PERIOD_LOCK request a closed world offers without
// closing another month: the permanent lock of the earliest closed month, asked by marcus through
// the API and decided by nobody — elena, the second Controller, opens its screen, the pass reads
// what the screen offers her, and marcus withdraws the request, so the world is left as it was.
import { Api, said, text } from "../api";
import type { Qa } from "../fixtures";
import { open } from "../observe";
import { flat } from "../record";
import { buttonsOf } from "../steps";
import { BOOK } from "../world";

const ENTITY = "AVM-US";

export async function lockScreensSection({ record, sessions }: Qa): Promise<void> {
  const marcus = await sessions.page("marcus");
  const elena = await sessions.page("elena");
  const requester = new Api(marcus);
  const decider = new Api(elena);
  let requestId = "";

  await record.check(
    {
      check: "P-1 a lock request on its own screen",
      persona: "marcus, elena",
      address: "/approvals/requests/<a PERIOD_LOCK request>",
      expected:
        "A PERIOD_LOCK request is decided by a Controller other than its requester (PRD SM-07, BR-CLS-02); the request's own screen offers her the decision (SCREENS SF-12:request), which is a way to a lock on the screens while the cockpit's control is unavailable (row C-10)",
    },
    async () => {
      const periods = await requester.list("/api/v1/periods", { entity: ENTITY, book: BOOK });
      // SM-07: a period is locked for good only after every earlier one; the earliest closed month.
      const month = periods.find((period) => text(period, "state") === "closed");
      if (month === undefined) {
        return {
          observed: `no period of ${ENTITY} ${BOOK} is closed: no permanent-lock request can be asked`,
          result: "not run",
        };
      }
      const key = text(month, "period", "period_key");
      const asked = await requester.send(
        "POST",
        `/api/v1/periods/${text(month, "id")}/request-permanent-lock`,
        { comment: "QA pass: asked to read where a lock request is decided; withdrawn at once." },
        { "If-Match": `"r${text(month, "row_version")}"` },
      );
      requestId = text(asked.json, "approval_request_id");
      if (requestId === "") {
        return {
          observed: `POST periods/<${key}>/request-permanent-lock → ${said(asked)} ${flat(text(asked.json, "detail"), 200)}`,
          result: "not run",
        };
      }
      const request = (await decider.get(`/api/v1/approvals/${requestId}`)).json;
      const seen = await open(elena, `/approvals/requests/${requestId}`);
      const form = elena.getByRole("form", { name: "Decision" });
      const offered = (await form.count()) === 0 ? [] : await buttonsOf(form.first());
      const approve = elena.getByRole("button", { name: "Approve", exact: true });
      const state =
        (await approve.count()) === 0
          ? "not offered"
          : `offered, aria-disabled ${(await approve.first().getAttribute("aria-disabled")) ?? "false"}`;
      // The cockpit of the same month as the same Controller: what it offers for the request.
      const cockpit = await open(elena, `/close/${ENTITY}/${BOOK}/${key}`);
      const main = await buttonsOf(elena.getByRole("main"));
      const observed = `${text(request, "request_no")} "${text(request, "summary")}" (${text(request, "subject", "type")}, ${text(request, "status")}), asked by marcus through the API for ${key}; as elena: can_decide ${String((request as { can_decide?: unknown } | null)?.can_decide)}; the request's screen is ${seen.state} ("${seen.heading}"), its Decision form offers [${offered.join(", ")}], "Approve" ${state}; the cockpit of ${key} is ${cockpit.state} and offers [${main.slice(0, 10).join(", ")}]. Nothing was decided.`;
      return {
        observed,
        result: state.startsWith("offered, aria-disabled false") ? "pass" : "seen once",
        page: elena,
      };
    },
  );

  if (requestId !== "") {
    const got = await requester.send("POST", `/api/v1/approvals/${requestId}/withdraw`, {
      comment: "QA pass: the request was asked only to read its screen.",
    });
    const after = text((await requester.get(`/api/v1/approvals/${requestId}`)).json, "status");
    record.note(
      `P: the permanent-lock request was withdrawn by marcus: POST withdraw → ${said(got)}; the request is ${after}`,
    );
  }
}
