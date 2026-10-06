// Reason field (DESIGN_SYSTEM DS-CMP-21; SCREENS_B SB-R-05). A textarea with a live character counter
// and a stated minimum: help "Minimum 10 characters", error "Enter at least 10 characters.". The check
// runs on blur, or at once after a submit attempt; the counter is announced politely at most every
// 500 ms (DS-A11Y-08). A caller that knows what belongs in the reason says so in a `hint`, one
// sentence the help shows before the minimum (SCREENS §8.4 rev 1.66, "Attest no change").
import { useEffect, useState } from "react";

import { announce } from "../../lib/a11y/announce";
import { t } from "../../lib/i18n/t";
import { cn } from "../ui/cn";
import { controlClass, Field } from "./Field";

export const REASON_MINIMUM = 10;
export const COUNTER_ANNOUNCE_MS = 500;

export function reasonLength(text: string): number {
  return [...text.trim()].length;
}

/** The SB-R-05 error for a reason shorter than the minimum, else null. */
export function reasonError(text: string, minimum = REASON_MINIMUM): string | null {
  return reasonLength(text) < minimum ? t("common.form.reason.tooShort", { count: minimum }) : null;
}

export interface ReasonFieldProps {
  readonly name?: string;
  readonly label: string;
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly minimum?: number;
  /** Shows the minimum check before blur, after a submit attempt. */
  readonly showError?: boolean;
  /** A server error mapped onto this field. */
  readonly error?: string | null | undefined;
  /**
   * What belongs in the reason, in one sentence. It stands before the minimum in the field's help,
   * so that it is part of what describes the field to assistive technology.
   */
  readonly hint?: string | undefined;
}

export function ReasonField({
  name = "reason",
  label,
  value,
  onChange,
  minimum = REASON_MINIMUM,
  showError = false,
  error,
  hint,
}: ReasonFieldProps) {
  const [touched, setTouched] = useState(false);
  const [typed, setTyped] = useState(false);
  const length = reasonLength(value);
  const shown = error ?? (touched || showError ? reasonError(value, minimum) : null);
  const stated = t("common.form.reason.minimum", { count: minimum });

  useEffect(() => {
    if (!typed) {
      return undefined;
    }
    const timer = setTimeout(() => {
      announce(t("common.form.reason.counter", { count: length }), "polite");
    }, COUNTER_ANNOUNCE_MS);
    return () => clearTimeout(timer);
  }, [length, typed]);

  return (
    <Field
      name={name}
      label={label}
      required
      help={hint === undefined ? stated : `${hint} ${stated}`}
      error={shown}
    >
      {(control) => (
        <div className="flex flex-col gap-1">
          <textarea
            {...control}
            value={value}
            rows={3}
            onChange={(event) => {
              setTyped(true);
              onChange(event.target.value);
            }}
            onBlur={() => setTouched(true)}
            className={cn(
              controlClass(shown !== null, true),
              "field-sizing-content max-h-50 min-h-20 resize-none",
            )}
          />
          <span aria-hidden="true" className="num self-end text-caption text-fg-3">
            {t("common.form.reason.counter", { count: length })}
          </span>
        </div>
      )}
    </Field>
  );
}
