// Fixtures for the witnesses of a refused command (docs/dev-guide.md DG-FE-06; SCREENS §0.7 SCR-ST-13):
// a problem whose `errors[]` names members, and what a control and a banner then say.
import { problemResponse } from "./msw";

export const REFUSAL_TITLE = "Check the highlighted fields";
/** The line every banner of a refused command ends with (PRD CPY-05), for `problemResponse`'s instance. */
export const REFUSAL_REFERENCE = "Reference 0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d.";
export const RECORD_CHANGED = "This record changed. Reload to see the latest version.";

export interface RefusedWith {
  readonly status?: number;
  readonly slug?: string;
  readonly title?: string;
  readonly detail?: string | null;
}

/**
 * A refusal (422 `validation-failed` unless said otherwise) whose `errors[]` holds one message for each
 * pointer given, in the order given; the pointer `""` stands for a message without a field.
 */
export function refusedWith(
  messages: Readonly<Record<string, string>>,
  {
    status = 422,
    slug = "validation-failed",
    title = REFUSAL_TITLE,
    detail = null,
  }: RefusedWith = {},
) {
  return problemResponse(slug, status, title, {
    detail,
    errors: Object.entries(messages).map(([field, message]) => ({
      field: field === "" ? null : field,
      sheet: null,
      row: null,
      rule_id: null,
      message,
    })),
  });
}

/** The texts a control is described by: its help and its error. */
export function describedBy(control: HTMLElement): string[] {
  return (control.getAttribute("aria-describedby") ?? "")
    .split(" ")
    .map((id) => document.getElementById(id)?.textContent ?? "");
}
