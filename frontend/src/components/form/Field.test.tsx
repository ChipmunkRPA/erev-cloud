// @vitest-environment jsdom
// DS-CMP-21 (DESIGN_SYSTEM §7.5; DS-A11Y-21; DG-FE-06): server errors map onto fields, the error summary
// takes focus and is announced assertively, and the submit button stays enabled.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { type FormEvent, useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { registerLiveRegions } from "../../lib/a11y/announce";
import { ApiProblem, fieldErrorsOf } from "../../lib/api/problems";
import { Button } from "../ui/Button";
import { ErrorSummary } from "./ErrorSummary";
import { controlClass, Field } from "./Field";

afterEach(() => {
  cleanup();
});

const FIELDS = [
  { name: "display_name", label: "Display name", help: "Shown to reviewers on approvals." },
  { name: "email", label: "Email", help: "Notifications go to this address." },
] as const;

// The problem a 422 validation-failed response carries (04 API-C-05).
const PROBLEM = new ApiProblem({
  type: "https://erev.dev/problems/validation-failed",
  slug: "validation-failed",
  title: "Validation failed",
  status: 422,
  detail: null,
  code: null,
  errors: [
    {
      field: "display_name",
      sheet: null,
      row: null,
      rule_id: null,
      message: "Enter a display name.",
    },
    {
      field: "email",
      sheet: null,
      row: null,
      rule_id: null,
      message: "Enter an email address such as ana@example.com.",
    },
  ],
  requestId: "req-1",
});

function ProfileForm() {
  const [errors, setErrors] = useState<Readonly<Record<string, string>>>({});
  const [submitCount, setSubmitCount] = useState(0);
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    setErrors(fieldErrorsOf(PROBLEM));
    setSubmitCount((count) => count + 1);
  };
  const entries = FIELDS.flatMap((field) => {
    const message = errors[field.name];
    return message === undefined ? [] : [{ name: field.name, message }];
  });
  return (
    <form onSubmit={onSubmit} noValidate>
      <ErrorSummary errors={entries} submitCount={submitCount} />
      {FIELDS.map((field) => (
        <Field
          key={field.name}
          name={field.name}
          label={field.label}
          help={field.help}
          error={errors[field.name]}
          required
        >
          {(control) => (
            <input {...control} className={controlClass(errors[field.name] !== undefined)} />
          )}
        </Field>
      ))}
      <Button type="submit" variant="primary">
        Save profile
      </Button>
    </form>
  );
}

describe("DS-CMP-21", () => {
  it("two server errors produce the focused, assertively announced summary; describedby lists error then help", () => {
    const polite = vi.fn();
    const assertive = vi.fn();
    const unregister = registerLiveRegions(polite, assertive);
    render(<ProfileForm />);

    const submit = screen.getByRole("button", { name: "Save profile" });
    fireEvent.click(submit);

    const heading = screen.getByRole("heading", { name: "Fix 2 fields to continue" });
    expect(document.activeElement).toBe(heading);
    expect(assertive).toHaveBeenCalledWith("Fix 2 fields to continue");
    expect(
      screen
        .getByRole("link", { name: "Enter an email address such as ana@example.com." })
        .getAttribute("href"),
    ).toBe("#field-email");

    const email = screen.getByRole("textbox", { name: "Email" });
    expect(email.getAttribute("aria-describedby")).toBe("field-email-error field-email-help");
    expect(email.getAttribute("aria-invalid")).toBe("true");
    expect(email.getAttribute("aria-required")).toBe("true");
    expect(document.getElementById("field-email-error")?.textContent).toBe(
      "Enter an email address such as ana@example.com.",
    );

    expect(submit.hasAttribute("disabled")).toBe(false);
    expect(submit.getAttribute("aria-disabled")).toBeNull();

    fireEvent.click(screen.getByRole("link", { name: "Enter a display name." }));
    expect(document.activeElement).toBe(screen.getByRole("textbox", { name: "Display name" }));
    unregister();
  });

  it("a field without an error describes the control by its help only", () => {
    render(
      <Field name="memo" label="Memo" optional help="Appears on the journal line.">
        {(control) => <input {...control} className={controlClass(false)} />}
      </Field>,
    );
    const memo = screen.getByRole("textbox", { name: "Memo (optional)" });
    expect(memo.getAttribute("aria-describedby")).toBe("field-memo-help");
    expect(memo.hasAttribute("aria-invalid")).toBe(false);
  });
});
