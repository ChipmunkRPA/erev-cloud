// Form field (DESIGN_SYSTEM DS-CMP-21, DS-A11Y-21; docs/dev-guide.md DG-FE-06). The label sits above
// the control, then the error message, then the help text. The control receives its id, name,
// `aria-describedby` (error id first, then help), `aria-invalid` and `aria-required` through a render
// function, so native inputs and the composite controls of this directory share one wrapper.
import type { ReactNode } from "react";

import { t } from "../../lib/i18n/t";
import { WarningCircle } from "../icons/registry";
import { cn } from "../ui/cn";

export interface FieldControlProps {
  readonly id: string;
  readonly name: string;
  readonly "aria-describedby"?: string;
  readonly "aria-invalid"?: true;
  readonly "aria-required"?: true;
}

/** DS-CMP-21 field widths: money 200 px, date 160 px, period 140 px, text up to 480 px. */
export type FieldWidth = "money" | "date" | "period" | "text" | "full";

export interface FieldProps {
  readonly name: string;
  readonly label: string;
  readonly optional?: boolean;
  readonly required?: boolean;
  readonly help?: string | undefined;
  readonly error?: string | null | undefined;
  readonly width?: FieldWidth;
  readonly children: (control: FieldControlProps) => ReactNode;
}

export function fieldId(name: string): string {
  return `field-${name}`;
}

export function fieldLabelId(name: string): string {
  return `${fieldId(name)}-label`;
}

const WIDTH: Readonly<Record<FieldWidth, string>> = {
  money: "w-50",
  date: "w-40",
  period: "w-35",
  text: "w-full max-w-120",
  full: "w-full",
};

/**
 * The DS-CMP-21 control style; `multiline` controls grow instead of holding the control height. Only a
 * read-only input or textarea loses its border: `:read-only` also matches every non-editable element,
 * which hid the border of the Select and MultiSelect triggers (L4-5-Q-58). It matches a DISABLED input
 * too, and its rule outranks `disabled:bg-subtle`: a disabled text or date field was a label with no box
 * under it. "Disabled" keeps its fill and its border (DESIGN_SYSTEM §7.5), so the rule excludes it.
 */
export function controlClass(invalid: boolean, multiline = false): string {
  return cn(
    "w-full rounded-md border bg-surface px-2.5 text-body text-fg-1 placeholder:text-fg-3 hover:border-fg-3 focus-visible:border-accent-solid disabled:bg-subtle disabled:text-fg-disabled [&:is(input,textarea):read-only:not(:disabled)]:border-transparent [&:is(input,textarea):read-only:not(:disabled)]:bg-transparent",
    multiline ? "min-h-[var(--control-h)] py-1" : "h-[var(--control-h)]",
    invalid ? "border-negative-fg" : "border-control",
  );
}

export function Field({
  name,
  label,
  optional = false,
  required = false,
  help,
  error,
  width = "full",
  children,
}: FieldProps) {
  const id = fieldId(name);
  const errorId = `${id}-error`;
  const helpId = `${id}-help`;
  const hasError = error !== undefined && error !== null && error !== "";
  const hasHelp = help !== undefined && help !== "";
  const describedBy = cn(hasError && errorId, hasHelp && helpId);
  const control: FieldControlProps = {
    id,
    name,
    ...(describedBy === "" ? {} : { "aria-describedby": describedBy }),
    ...(hasError ? { "aria-invalid": true as const } : {}),
    ...(required ? { "aria-required": true as const } : {}),
  };
  return (
    <div className={cn("flex flex-col gap-1", WIDTH[width])}>
      <label id={fieldLabelId(name)} htmlFor={id} className="text-body-sm font-medium text-fg-1">
        {label}
        {optional ? (
          <span className="ms-1 font-normal text-fg-3">{t("common.form.optional")}</span>
        ) : null}
      </label>
      {children(control)}
      {hasError ? (
        <p id={errorId} className="flex items-start gap-1 text-body-sm text-negative-fg">
          <WarningCircle aria-hidden="true" className="mt-0.5 shrink-0" />
          {error}
        </p>
      ) : null}
      {hasHelp ? (
        <p id={helpId} className="text-body-sm text-fg-3">
          {help}
        </p>
      ) : null}
    </div>
  );
}
