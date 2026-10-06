// @vitest-environment jsdom
// A refused command at the fields of its form (DESIGN_SYSTEM DS-CMP-21; SCREENS §11.0 "Refused
// command", rev 1.31; SCREENS_B §9.15 rev 1.62): the banner beside the fields says what no field says,
// does not repeat a sentence a field shows, and leaves once it has nothing left to point at.
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ApiProblem, type ProblemFieldError } from "./problems";
import {
  bannerProblem,
  fieldMessages,
  placeProblem,
  placeProblemByEnd,
  useFieldRefusals,
} from "./refusals";

function problem(detail: string | null, errors: readonly Partial<ProblemFieldError>[]): ApiProblem {
  return new ApiProblem({
    type: "https://erev.dev/problems/validation-failed",
    slug: "validation-failed",
    title: "Check the highlighted fields",
    status: 422,
    detail,
    code: null,
    requestId: "0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d",
    errors: errors.map((error) => ({
      field: null,
      sheet: null,
      row: null,
      rule_id: null,
      message: "",
      ...error,
    })),
  });
}

const MEMBERS = { effective: ["effective_from"], name: ["name"] } as const;
// PRD §5.5 ERR-75: the problem's detail is the message of its one error.
const SENTENCE =
  "This version replaces a published one. Choose an effective date later than today.";

describe("a refusal beside the fields of its form", () => {
  it("the banner does not repeat a detail that a field shows, and keeps one no field shows", () => {
    const repeated = problem(SENTENCE, [{ field: "effective_from", message: SENTENCE }]);
    const shown = bannerProblem(repeated, placeProblem(repeated, MEMBERS));
    expect(shown.detail).toBeNull();
    expect(shown.title).toBe("Check the highlighted fields");
    expect(shown.requestId).toBe(repeated.requestId);

    const counted = problem("1 field needs attention.", [
      { field: "effective_from", message: SENTENCE },
    ]);
    // Nothing to add or to drop: the problem is shown as it came.
    expect(bannerProblem(counted, placeProblem(counted, MEMBERS))).toBe(counted);
  });

  it("the banner lists the messages of members the form has no field for", () => {
    const refused = problem(null, [
      { field: "status", message: "Run the tests of this version before submitting it." },
      { field: "name", message: "Use 1 to 400 characters." },
    ]);
    const shown = bannerProblem(refused, placeProblem(refused, MEMBERS));
    expect(shown.errors.filter((error) => error.field === null)).toEqual([
      {
        field: null,
        sheet: null,
        row: null,
        rule_id: null,
        message: "Run the tests of this version before submitting it.",
      },
    ]);
  });

  it("the banner says a sentence once, however many members without a field carry it", () => {
    // 04 API-R-23: every unknown key of `policy_values` is refused with the same sentence.
    const unknown = "Use the code of a policy parameter.";
    const refused = problem(null, [
      { field: "policy_values.x.one", message: unknown },
      { field: "policy_values.x.two", message: unknown },
      { field: null, message: "Ask an administrator." },
      { field: "status", message: "Ask an administrator." },
    ]);
    const placed = placeProblem(refused, MEMBERS);
    expect(placed.unplaced).toEqual([unknown, "Ask an administrator."]);
    expect(
      bannerProblem(refused, placed)
        .errors.filter((error) => error.field === null)
        .map((error) => error.message),
    ).toEqual(["Ask an administrator.", unknown]);
  });

  it("the banner does not list a sentence its detail already says", () => {
    // PRD ERR-92 as the API sends it (`registry_versions._reopenable`): a refusal by name carries
    // its sentence as the detail and as the message on `status`, a member no form has a field for.
    const superseded =
      "Version 4 was published after this version was submitted. Create a new version: it starts from the published values.";
    const refused = problem(superseded, [{ field: "status", message: superseded }]);
    const shown = bannerProblem(refused, placeProblem(refused, MEMBERS));
    expect(shown.detail).toBe(superseded);
    expect(shown.errors.filter((error) => error.field === null)).toEqual([]);
    // Another sentence on the same member is still listed beside the detail.
    const open = "Another version is open. Finish it or withdraw it first.";
    const both = problem(superseded, [
      { field: "status", message: superseded },
      { field: "status", message: open },
    ]);
    expect(
      bannerProblem(both, placeProblem(both, MEMBERS))
        .errors.filter((error) => error.field === null)
        .map((error) => error.message),
    ).toEqual([open]);
  });

  it("a banner that only points at the fields leaves once each refused field has been edited", () => {
    const refused = problem(SENTENCE, [
      { field: "effective_from", message: SENTENCE },
      { field: "name", message: "Use 1 to 400 characters." },
    ]);
    const { result } = renderHook(() => useFieldRefusals(refused, MEMBERS));
    expect(result.current.fields).toEqual({
      effective: SENTENCE,
      name: "Use 1 to 400 characters.",
    });
    expect(result.current.banner?.detail).toBeNull();

    act(() => {
      result.current.edited("effective");
    });
    // One refused field still shows its message: the banner still points at it.
    expect(result.current.fields).toEqual({ effective: null, name: "Use 1 to 400 characters." });
    expect(result.current.banner).not.toBeNull();

    act(() => {
      result.current.edited("name");
    });
    expect(result.current.fields).toEqual({ effective: null, name: null });
    expect(result.current.banner).toBeNull();
  });

  it("a banner that says something of its own stays when the refused fields have been edited", () => {
    const refused = problem("2 fields need attention.", [
      { field: "effective_from", message: SENTENCE },
      { field: "status", message: "Run the tests of this version before submitting it." },
    ]);
    const { result } = renderHook(() => useFieldRefusals(refused, MEMBERS));
    act(() => {
      result.current.edited("effective");
    });
    expect(result.current.fields.effective).toBeNull();
    expect(result.current.banner?.detail).toBe("2 fields need attention.");
    expect(
      result.current.banner?.errors.filter((error) => error.field === null).map((e) => e.message),
    ).toEqual(["Run the tests of this version before submitting it."]);
  });

  it("a banner that lists a message of a member without a field stays, though the problem has no detail", () => {
    const refused = problem(null, [
      { field: "effective_from", message: SENTENCE },
      { field: "status", message: "Run the tests of this version before submitting it." },
    ]);
    const { result } = renderHook(() => useFieldRefusals(refused, MEMBERS));
    act(() => {
      result.current.edited("effective");
    });
    expect(result.current.fields.effective).toBeNull();
    expect(
      result.current.banner?.errors.filter((error) => error.field === null).map((e) => e.message),
    ).toEqual(["Run the tests of this version before submitting it."]);
  });

  it("a refusal that names no field of the form is shown whole, and a new refusal shows its fields again", () => {
    const first = problem(null, [{ field: "effective_from", message: SENTENCE }]);
    const second = problem(null, [{ field: "effective_from", message: SENTENCE }]);
    const { result, rerender } = renderHook(
      ({ refused }: { readonly refused: ApiProblem | null }) => useFieldRefusals(refused, MEMBERS),
      { initialProps: { refused: first as ApiProblem | null } },
    );
    act(() => {
      result.current.edited("effective");
    });
    expect(result.current.banner).toBeNull();
    // The same sentence for the value sent next is a new refusal.
    rerender({ refused: second });
    expect(result.current.fields.effective).toBe(SENTENCE);
    expect(result.current.banner).toBe(second);
    rerender({ refused: null });
    expect(result.current.banner).toBeNull();
    expect(result.current.fields).toEqual({ effective: null, name: null });
  });
  // docs/dev-guide.md DG-FE-06 rev 1.228 (item KIT-UNPLACED-ERRORS-1): the second placing, for a drawer
  // whose body nests what its fields send.
  it("a drawer places by the end of the pointer, and what no field ends is left for the banner", () => {
    const refused = problem(null, [
      { field: "questionnaire.event_c_met_on", message: "Enter the date the criterion was met." },
      { field: "lines[0].rationale", message: "Say why in at least 10 characters." },
      { field: "contract_ids[1]", message: "This contract is already in a group." },
      { field: "lines[1].rationale", message: "A second sentence of the same field." },
    ]);
    const placed = placeProblemByEnd(refused, {
      met: ["questionnaire.event_c_met_on"],
      rationale: ["rationale"],
    });
    expect(placed.fields).toEqual({
      met: "Enter the date the criterion was met.",
      rationale: "Say why in at least 10 characters.",
    });
    // The field shows its first message; the second, a different sentence, is the banner's.
    expect(placed.unplaced).toEqual([
      "This contract is already in a group.",
      "A second sentence of the same field.",
    ]);
    expect(
      bannerProblem(refused, placed)
        .errors.filter((error) => error.field === null)
        .map((error) => error.message),
    ).toEqual(["This contract is already in a group.", "A second sentence of the same field."]);
    // The two placings differ on a nested pointer: the first member of `lines[0].rationale` is `lines`.
    expect(placeProblem(refused, { rationale: ["rationale"] }).fields.rationale).toBeNull();
  });

  // DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): a field shows one message, so a further message
  // that names the same field was shown nowhere. It is the banner's, unless it says the sentence the
  // field already shows.
  it("a further, different message for a field that shows one is listed by the banner", () => {
    const first = "Use a positive amount.";
    const second = "Use at most two decimal places.";
    const refused = problem(null, [
      { field: "amount", message: first },
      { field: "amount", message: second },
      { field: "amount", message: first },
      { field: "lines[0].amount", message: first },
      { field: "lines[1].amount", message: second },
    ]);
    for (const placed of [
      placeProblem(refused, { amount: ["amount"], lines: ["lines"] }),
      placeProblemByEnd(refused, { amount: ["amount"] }),
    ]) {
      expect(placed.fields.amount).toBe(first);
      expect(placed.unplaced).toEqual([second]);
      expect(
        bannerProblem(refused, placed)
          .errors.filter((error) => error.field === null)
          .map((error) => error.message),
      ).toEqual([second]);
    }
  });

  it("the messages of the fields are the fields that have one", () => {
    expect(fieldMessages({ code: "Use letters.", name: null })).toEqual({ code: "Use letters." });
  });
});
