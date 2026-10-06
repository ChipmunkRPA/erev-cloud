// Shared parts of the SF-03 command drawers (SCREENS §4.9; DESIGN_SYSTEM DS-CMP-09, DS-CMP-21): the
// radio group and the text, select and evidence fields, the refresh of every workbench read after a
// command, and the request number of a routed approval (BR-REC-01). A refused command is shown by
// `RefusalBanner` of src/components/feedback (docs/dev-guide.md DG-FE-06): the banner this module held
// said the title, the detail and the messages without a field, and dropped every other sentence.
import { useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useId } from "react";

import { Banner } from "../../../components/feedback/Banner";
import { controlClass, Field, type FieldWidth } from "../../../components/form/Field";
import { Select } from "../../../components/form/Select";
import type { CommandKeys } from "../../../lib/api/commands";
import type { ApiProblem } from "../../../lib/api/problems";
import {
  type ApprovalItem,
  CONTRACT_RECORD_KEYS,
  readJson,
} from "../../../lib/api/queries/contracts";
import { uploadFile } from "../../../lib/api/queries/ssp-books";
import { t } from "../../../lib/i18n/t";

/** 04 E-51 purpose of an evidence file (API-R-12). */
export const EVIDENCE_PURPOSE = "ATTACHMENT";

/** Refreshes every read of the workbench and the contract lists. */
export function useRefreshRecord(): () => Promise<void> {
  const queryClient = useQueryClient();
  return async () => {
    await Promise.all(
      CONTRACT_RECORD_KEYS.map((queryKey) => queryClient.invalidateQueries({ queryKey })),
    );
  };
}

/** The request number of a routed approval request; the id itself when it cannot be read. */
export async function requestNumber(requestId: string): Promise<string> {
  try {
    return (await readJson<ApprovalItem>(`/api/v1/approvals/${requestId}`)).data.request_no;
  } catch {
    return requestId;
  }
}

/** Uploads each evidence file (`POST /files`, keyed by `keys`) and returns the stored file ids. */
export async function uploadEvidence(keys: CommandKeys, files: readonly File[]): Promise<string[]> {
  const ids: string[] = [];
  for (const file of files) {
    ids.push((await uploadFile(keys, EVIDENCE_PURPOSE, file)).id);
  }
  return ids;
}

/**
 * The field error of a problem, matched on the end of its pointer. One caller is left, the estimate
 * element drawer (routes/contracts/estimates.tsx), whose banner lists what its fields do not show; every
 * other form places with src/lib/api/refusals.ts, and no new caller joins (frontend/config).
 */
export function fieldError(problem: ApiProblem | null, ...names: readonly string[]): string | null {
  if (problem === null) {
    return null;
  }
  for (const error of problem.errors) {
    if (error.field !== null && names.some((name) => error.field?.endsWith(name) === true)) {
      return error.message;
    }
  }
  return null;
}

export interface Choice<T extends string> {
  readonly value: T;
  readonly label: string;
}

export interface RadioGroupProps<T extends string> {
  readonly legend: string;
  readonly options: readonly Choice<T>[];
  readonly value: T | null;
  readonly onChange: (value: T) => void;
  readonly error?: string | null | undefined;
}

export function RadioGroup<T extends string>({
  legend,
  options,
  value,
  onChange,
  error,
}: RadioGroupProps<T>) {
  const name = useId();
  const errorId = useId();
  const invalid = error !== null && error !== undefined;
  return (
    <fieldset className="flex flex-col gap-2" aria-describedby={invalid ? errorId : undefined}>
      <legend className="mb-1 text-body-sm font-medium text-fg-1">{legend}</legend>
      {options.map((option) => (
        <label key={option.value} className="flex items-center gap-2 text-body text-fg-1">
          <input
            type="radio"
            name={name}
            value={option.value}
            checked={value === option.value}
            onChange={() => onChange(option.value)}
          />
          {option.label}
        </label>
      ))}
      {invalid ? (
        <p id={errorId} className="text-body-sm text-negative-fg">
          {error}
        </p>
      ) : null}
    </fieldset>
  );
}

export interface TextFieldProps {
  readonly name: string;
  readonly label: string;
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly optional?: boolean;
  readonly required?: boolean;
  readonly readOnly?: boolean;
  /** DS-CMP-21 "Disabled": shown and not editable, where the page states why. */
  readonly disabled?: boolean;
  readonly help?: string | undefined;
  readonly error?: string | null | undefined;
  readonly width?: FieldWidth;
  readonly inputMode?: "text" | "decimal" | "numeric";
  readonly multiline?: boolean;
}

export function TextField({
  name,
  label,
  value,
  onChange,
  optional = false,
  required = false,
  readOnly = false,
  disabled = false,
  help,
  error,
  width = "text",
  inputMode = "text",
  multiline = false,
}: TextFieldProps) {
  const invalid = error !== null && error !== undefined;
  return (
    <Field
      name={name}
      label={label}
      optional={optional}
      required={required}
      help={help}
      error={error}
      width={width}
    >
      {(control) =>
        multiline ? (
          <textarea
            {...control}
            value={value}
            rows={3}
            readOnly={readOnly}
            disabled={disabled}
            onChange={(event) => onChange(event.target.value)}
            className={controlClass(invalid, true)}
          />
        ) : (
          <input
            {...control}
            type="text"
            inputMode={inputMode}
            value={value}
            readOnly={readOnly}
            disabled={disabled}
            onChange={(event) => onChange(event.target.value)}
            className={controlClass(invalid)}
          />
        )
      }
    </Field>
  );
}

export interface SelectFieldProps<T extends string> {
  readonly name: string;
  readonly label: string;
  readonly options: readonly Choice<T>[];
  readonly value: T | null;
  readonly onChange: (value: T) => void;
  readonly optional?: boolean;
  readonly error?: string | null | undefined;
}

export function SelectField<T extends string>({
  name,
  label,
  options,
  value,
  onChange,
  optional = false,
  error,
}: SelectFieldProps<T>) {
  return (
    <Field name={name} label={label} optional={optional} error={error} width="text">
      {(control) => (
        <Select
          control={control}
          options={options}
          value={value}
          onChange={onChange}
          invalid={error !== null && error !== undefined}
        />
      )}
    </Field>
  );
}

export interface EvidenceFieldProps {
  readonly name: string;
  readonly label: string;
  readonly required?: boolean;
  readonly files: readonly File[];
  readonly onChange: (files: readonly File[]) => void;
  readonly error?: string | null | undefined;
}

/** Evidence attachments: a native file input; the files upload when the command is sent. */
export function EvidenceField({
  name,
  label,
  required = false,
  files,
  onChange,
  error,
}: EvidenceFieldProps) {
  return (
    <Field
      name={name}
      label={label}
      optional={!required}
      required={required}
      help={t("contracts.drawer.evidenceHelp")}
      error={error}
      width="text"
    >
      {(control) => (
        <span className="flex flex-col gap-1">
          <input
            {...control}
            type="file"
            multiple
            onChange={(event) => onChange(Array.from(event.target.files ?? []))}
            className="text-body-sm text-fg-1"
          />
          {files.length === 0 ? null : (
            <span className="text-body-sm text-fg-2">
              {files.map((file) => file.name).join(", ")}
            </span>
          )}
        </span>
      )}
    </Field>
  );
}

/** A definition list row of a drawer's read-only part. */
export function ReadOnlyItem({
  label,
  children,
}: {
  readonly label: string;
  readonly children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-caption text-fg-3">{label}</dt>
      <dd className="text-body text-fg-1">{children}</dd>
    </div>
  );
}

/**
 * The preview of a dry run that this reader is not shown (SCREENS §4.9.3 and §8.4 rev 1.79; 04
 * API-S-Job `result` rev 1.314; `summaryWithheld` of src/lib/api/jobs.ts). The dry run of pending
 * events and of an estimate version keeps no document: its job answers the summary, which holds
 * figures of the whole combination group, to a reader who holds `contract.read` for every entity of
 * the group. The notice stands where the figures would, under the panel's title "Preview"; the job
 * answers this reader no figure, so none stands beside it. It follows a dry run the drawer asked
 * for: it is inserted after load, and announced.
 */
export function PreviewNotShown() {
  return (
    <Banner
      tone="info"
      title={t("contracts.drawer.preview.withheld.title")}
      announce="live"
      headingLevel={4}
    >
      <p>{t("contracts.drawer.preview.withheld.text")}</p>
    </Banner>
  );
}

/** "Yes" and "No" choices of 04 boolean members. */
export function yesNoChoices(): readonly Choice<"YES" | "NO">[] {
  return [
    { value: "YES", label: t("contracts.drawer.yes") },
    { value: "NO", label: t("contracts.drawer.no") },
  ];
}

const DECIMAL = /^\d+(?:\.\d+)?$/;

/** A non-negative decimal string, or null; `positive` refuses zero. */
export function decimalText(text: string, positive = false): string | null {
  const value = text.trim().replace(/,/g, "");
  if (!DECIMAL.test(value)) {
    return null;
  }
  if (positive && /^0+(?:\.0+)?$/.test(value)) {
    return null;
  }
  return value;
}

/**
 * A percent input as a ratio string without floating point: "45" → "0.45", "12.5" → "0.125",
 * "100" → "1". Null for text that is not a decimal between 0 and 100.
 */
export function percentToRatio(text: string): string | null {
  const match = /^(\d+)(?:\.(\d+))?$/.exec(text.trim());
  if (match === null) {
    return null;
  }
  const integer = match[1] ?? "0";
  const fraction = match[2] ?? "";
  const digits = `${integer}${fraction}`.replace(/^0+(?=\d)/, "");
  const scale = fraction.length + 2;
  const padded = digits.padStart(scale + 1, "0");
  const whole = padded.slice(0, padded.length - scale).replace(/^0+(?=\d)/, "");
  const part = padded.slice(padded.length - scale).replace(/0+$/, "");
  if (whole !== "0" && !(whole === "1" && part === "")) {
    return null;
  }
  return part === "" ? whole : `${whole}.${part}`;
}
