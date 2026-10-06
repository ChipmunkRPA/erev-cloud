// Error summary (DESIGN_SYSTEM DS-CMP-21, DS-CMP-29, DS-A11Y-21). With two or more errors on submit a
// negative banner "Fix <n> fields to continue" heads the form and links to each field; focus moves to its
// heading and the title is announced assertively (DS-A11Y-08). Submit buttons stay enabled.
import { useEffect, useRef } from "react";

import { announce } from "../../lib/a11y/announce";
import { t } from "../../lib/i18n/t";
import { Banner } from "../feedback/Banner";
import { fieldId } from "./Field";

/** A field error; the specific message is the link text (DS-CMP-21). */
export interface FormErrorEntry {
  readonly name: string;
  readonly message: string;
}

export interface ErrorSummaryProps {
  readonly errors: readonly FormErrorEntry[];
  /** Increments on every submit, so a repeated failed submit moves focus to the summary again. */
  readonly submitCount: number;
}

export function ErrorSummary({ errors, submitCount }: ErrorSummaryProps) {
  const heading = useRef<HTMLHeadingElement>(null);
  const handled = useRef(0);
  const title = errors.length >= 2 ? t("common.form.errorSummary", { count: errors.length }) : null;

  useEffect(() => {
    if (title === null || submitCount === handled.current) {
      return;
    }
    handled.current = submitCount;
    heading.current?.focus();
    announce(title, "assertive");
  }, [submitCount, title]);

  if (title === null) {
    return null;
  }
  return (
    <Banner tone="negative" announce="static" title={title} titleRef={heading}>
      <ul className="flex flex-col gap-0.5">
        {errors.map((error) => (
          <li key={error.name}>
            <a
              href={`#${fieldId(error.name)}`}
              className="text-fg-1 underline"
              onClick={(event) => {
                event.preventDefault();
                document.getElementById(fieldId(error.name))?.focus();
              }}
            >
              {error.message}
            </a>
          </li>
        ))}
      </ul>
    </Banner>
  );
}
