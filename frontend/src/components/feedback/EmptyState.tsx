// Empty state (DESIGN_SYSTEM DS-CMP-23; REQ-UX-016). Text first, start-aligned: a heading naming what
// belongs here, at most two sentences on why it is empty and what to do, the next action and an
// optional link such as the sample dataset. No illustrations or large icons (D-62).
import type { ReactNode } from "react";

import type { Icon } from "../icons/registry";
import { Button } from "../ui/Button";

export interface EmptyStateProps {
  readonly title: string;
  readonly description: string;
  /**
   * The identifiers the description names, for example a permission's code: each occurrence is set
   * in mono, as an identifier beside body text is (DS-TYP-10, DS-TYP-18).
   */
  readonly identifiers?: readonly string[] | undefined;
  readonly action?: { readonly label: string; readonly onAction: () => void } | undefined;
  /** An optional secondary link, for example "Load the sample SaaS dataset". */
  readonly link?: { readonly label: string; readonly href: string } | undefined;
  readonly icon?: Icon | undefined;
  readonly headingLevel?: 2 | 3 | 4;
  readonly children?: ReactNode;
}

// Copy defects throw in development and tests; a production build still renders.
const STRICT = import.meta.env.DEV || import.meta.env.MODE === "test";

export function sentenceCount(text: string): number {
  return (text.trim().match(/[.!?](?=\s|$)/g) ?? []).length;
}

/** The text with every occurrence of an identifier set in mono (DS-TYP-10). */
function withIdentifiers(text: string, identifiers: readonly string[]): ReactNode {
  // The longest first, so that an identifier that begins another is not cut out of it.
  const known = [...new Set(identifiers)]
    .filter((identifier) => identifier !== "")
    .sort((one, other) => other.length - one.length);
  if (known.length === 0) {
    return text;
  }
  const parts: ReactNode[] = [];
  let rest = text;
  while (rest !== "") {
    let at = -1;
    let found = "";
    for (const identifier of known) {
      const index = rest.indexOf(identifier);
      if (index !== -1 && (at === -1 || index < at)) {
        at = index;
        found = identifier;
      }
    }
    if (at === -1) {
      parts.push(rest);
      break;
    }
    if (at > 0) {
      parts.push(rest.slice(0, at));
    }
    parts.push(
      <span key={parts.length} className="font-mono text-mono">
        {found}
      </span>,
    );
    rest = rest.slice(at + found.length);
  }
  return parts;
}

export function EmptyState({
  title,
  description,
  identifiers = [],
  action,
  link,
  icon: TitleIcon,
  headingLevel = 2,
}: EmptyStateProps) {
  if (STRICT && sentenceCount(description) > 2) {
    throw new Error("An empty state description has at most two sentences (DS-CMP-23)");
  }
  const Heading = `h${String(headingLevel)}` as "h2" | "h3" | "h4";
  return (
    <div className="flex max-w-120 flex-col items-start gap-2 pt-12">
      <div className="flex items-center gap-2">
        {TitleIcon === undefined ? null : (
          <TitleIcon aria-hidden="true" size={20} className="shrink-0 text-fg-3" />
        )}
        <Heading className="text-title-sm text-fg-1">{title}</Heading>
      </div>
      <p className="text-body-sm text-fg-2">{withIdentifiers(description, identifiers)}</p>
      {action === undefined && link === undefined ? null : (
        <div className="mt-2 flex flex-wrap items-center gap-4">
          {action === undefined ? null : (
            <Button variant="primary" onClick={action.onAction}>
              {action.label}
            </Button>
          )}
          {link === undefined ? null : (
            <a
              href={link.href}
              className="text-body-sm text-accent-fg hover:text-accent-fg-hover hover:underline"
            >
              {link.label}
            </a>
          )}
        </div>
      )}
    </div>
  );
}
