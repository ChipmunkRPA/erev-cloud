// @vitest-environment jsdom
// RefusalBanner (DESIGN_SYSTEM DS-CMP-29; docs/dev-guide.md DG-FE-06 rev 1.228; SCREENS §0.7 rev 1.47;
// item KIT-UNPLACED-ERRORS-1): a refused command is never shown nowhere. A form that names no members
// is shown every sentence of `errors[]`, each once; a form that places messages at its fields is shown
// what no field took; the 412 line stands in place of a refusal.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ApiProblem, type ProblemFieldError } from "../../lib/api/problems";
import { placeProblem } from "../../lib/api/refusals";
import { RefusalBanner } from "./RefusalBanner";

afterEach(() => {
  cleanup();
});

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

const STUDY = "Choose a study that is approved.";
const NAME = "Use 1 to 400 characters.";
const WHOLE = "The version has no entries.";

function lines(): string[] {
  return Array.from(
    screen.getByRole("alert").querySelectorAll("p"),
    (line) => line.textContent ?? "",
  );
}

describe("RefusalBanner", () => {
  it("a form that names no members is shown every sentence of the refusal, each once", () => {
    render(
      <RefusalBanner
        problem={problem(null, [
          { field: "study_id", message: STUDY },
          { field: "name", message: NAME },
          { message: WHOLE },
          { field: "source_run_id", message: STUDY },
        ])}
      />,
    );
    const banner = screen.getByRole("alert");
    expect(
      within(banner).getByRole("heading", { name: "Check the highlighted fields" }),
    ).toBeTruthy();
    expect(lines()).toEqual([
      STUDY,
      NAME,
      WHOLE,
      "Reference 0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d.",
    ]);
  });

  it("a form that places messages at its fields is shown what no field took", () => {
    const refused = problem("2 fields need attention.", [
      { field: "study_id", message: STUDY },
      { field: "name", message: NAME },
    ]);
    render(<RefusalBanner problem={refused} placed={placeProblem(refused, { name: ["name"] })} />);
    expect(lines()).toEqual([
      "2 fields need attention.",
      STUDY,
      "Reference 0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d.",
    ]);
  });

  it("a detail is said once: not again as a sentence, and not at all when a field shows it", () => {
    const repeated = problem(NAME, [{ field: "name", message: NAME }]);
    const view = render(<RefusalBanner problem={repeated} />);
    expect(lines()).toEqual([NAME, "Reference 0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d."]);
    view.rerender(
      <RefusalBanner problem={repeated} placed={placeProblem(repeated, { name: ["name"] })} />,
    );
    expect(lines()).toEqual(["Reference 0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d."]);
  });

  // PRD ERR-86 (lane F-CLO-A): the cancel of a journal run answers one sentence as `detail` and as
  // its one message without a field.
  it("a sentence the detail says is not listed again, with or without a field", () => {
    const sentence = "The ledger still holds entries of this run. Reverse them before you cancel.";
    render(<RefusalBanner problem={problem(sentence, [{ message: sentence }])} />);
    expect(lines()).toEqual([sentence, "Reference 0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d."]);
  });

  // SCREENS §4.9.1 (rev 1.72): a form that knows the way out of a refusal hands the banner its action.
  it("a form's action stands under the sentences of the refusal, and not beside the line of a 412 or without a problem", () => {
    const refused = problem(STUDY, [{ field: "events.0.payload.study_id", message: STUDY }]);
    const action = <button type="button">Choose another study</button>;
    const view = render(<RefusalBanner problem={refused} actions={action} />);
    const banner = screen.getByRole("alert");
    const offered = within(banner).getByRole("button", { name: "Choose another study" });
    // After the last sentence of the problem, its reference.
    const reference = within(banner).getByText("Reference 0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d.");
    expect(
      reference.compareDocumentPosition(offered) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(lines()).toEqual([STUDY, "Reference 0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d."]);

    view.rerender(
      <RefusalBanner
        problem={refused}
        actions={action}
        conflict="This record changed. Reload to see the latest version."
      />,
    );
    expect(screen.queryByRole("button", { name: "Choose another study" })).toBeNull();
    view.rerender(<RefusalBanner problem={null} actions={action} />);
    expect(screen.queryByRole("button")).toBeNull();
    // A banner that is handed no action holds no row for one.
    view.rerender(<RefusalBanner problem={refused} />);
    expect(within(screen.getByRole("alert")).queryByRole("button")).toBeNull();
  });

  it("a record that changed under the member is said in place of the refusal; no problem, no banner", () => {
    const view = render(
      <RefusalBanner
        problem={problem(null, [{ field: "name", message: NAME }])}
        conflict="This record changed. Reload to see the latest version."
      />,
    );
    expect(screen.queryByRole("alert")).toBeNull();
    expect(
      screen.getByRole("heading", {
        name: "This record changed. Reload to see the latest version.",
      }),
    ).toBeTruthy();
    expect(screen.queryByText(NAME)).toBeNull();
    view.rerender(<RefusalBanner problem={null} />);
    expect(screen.queryByRole("heading")).toBeNull();
  });
});
