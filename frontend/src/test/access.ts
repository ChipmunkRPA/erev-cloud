// The access-limited state in a test (SCREENS §0.6 SCR-PERM-01, §0.7 SCR-ST-06; DS-CMP-23). Its
// description names a permission by a phrase and, in parentheses and in mono, by its code, so the
// sentence is one paragraph of several nodes: a query by text does not find it whole.
import { screen } from "@testing-library/react";

/** The description of the access-limited state on screen, whole; the heading names the area. */
export function accessDescription(): string {
  const heading = screen.getByRole("heading", { name: /^You do not have access to / });
  return heading.parentElement?.nextElementSibling?.textContent ?? "";
}

/** The codes the description sets in mono, in order (DS-TYP-10). */
export function accessDescriptionCodes(): readonly string[] {
  const heading = screen.getByRole("heading", { name: /^You do not have access to / });
  const paragraph = heading.parentElement?.nextElementSibling;
  return Array.from(paragraph?.querySelectorAll("span.font-mono") ?? []).map(
    (code) => code.textContent,
  );
}
