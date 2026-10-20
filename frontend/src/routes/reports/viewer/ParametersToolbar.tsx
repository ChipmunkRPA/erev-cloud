// RV-08 Parameters toolbar (SCREENS_B §0.5, §5.2; §5.6 parameter tables; DESIGN_SYSTEM DS-CMP-13,
// DS-CMP-21, DS-CMP-31; D-87 L6-3-Q-20). The report's own parameters in §5.6 order in one wrapping row,
// then "Run report". Context keys (entity, book, period) stay on the context pill, and the source on
// RV-04. `currency_view` is a field of the reports that take it, so the fail-closed 422 on
// `parameters.currency_view` shows as that field's error. While a lock snapshot is the source the
// fields are shown and unavailable (RV-04 rev 1.98; ENGINE_SPEC_B S15-R-19): an as-locked run is the
// lock's entity, book and period and takes no other parameter, so a field that could be changed would
// only be a refusal. The page says so under the fields, and "Run report" stays: a report run reads
// the source and is not a command (D-88 L7-3-Q-2).
import { type ReactNode, useId, useState } from "react";

import { DateInput } from "../../../components/form/DateInput";
import { Field } from "../../../components/form/Field";
import { Select } from "../../../components/form/Select";
import { Button } from "../../../components/ui/Button";
import { SegmentedControl } from "../../../components/ui/SegmentedControl";
import { Tooltip } from "../../../components/ui/Tooltip";
import type { ReportDefinition } from "../../../lib/api/queries/reports";
import { periodLabel } from "../../../lib/api/queries/tenant";
import { formatDate, NO_VALUE } from "../../../lib/format";
import { hasMessage, t } from "../../../lib/i18n/t";
import { TextField } from "../../contracts/drawers/common";
import { parameterKeys, supportsLockedCurrency, type ReportContext } from "./specs";
import { CloseLockParameter } from "./CloseLockParameter";
import { MigrationParameter } from "./MigrationParameter";
import { ReportFilters } from "./ReportFilters";
import { filterRows, validFilterRows } from "./filterValues";

/**
 * The keys a toolbar field edits, in §5.6 parameter-table order; every other key is context or source.
 * A stored `parameters_schema` keeps JSONB key order (by length), not the table order (L7-3-Q-6).
 */
const FIELD_ORDER: readonly string[] = [
  "mode",
  "known_since",
  "from_period_key",
  "to_period_key",
  "from_date",
  "to_date",
  "time_bands",
  "row_dimension",
  "granularity",
  "measure",
  "contract_external_id",
  "currency_view",
];

const CURRENCY_VIEWS = ["transaction", "functional", "reporting"] as const;

function enumOf(definition: ReportDefinition, key: string): readonly string[] {
  const properties = definition.parameters_schema.properties as
    Readonly<Record<string, { readonly enum?: unknown }>> | undefined;
  const values = properties?.[key]?.enum;
  return Array.isArray(values)
    ? values.filter((item): item is string => typeof item === "string")
    : [];
}

/** The toolbar fields of a definition in §5.6 order. */
const CONTEXT_KEYS = new Set([
  "entity_codes",
  "book",
  "period_key",
  "period_lock_id",
  "known_at",
  "known_at_basis",
]);
function schemaOf(definition: ReportDefinition, key: string): Readonly<Record<string, unknown>> {
  const properties = definition.parameters_schema.properties as
    Record<string, Record<string, unknown>> | undefined;
  return properties?.[key] ?? {};
}

export function toolbarKeys(definition: ReportDefinition): readonly string[] {
  const declared = parameterKeys(definition);
  const ordered = FIELD_ORDER.filter((key) => declared.includes(key));
  const additional = declared.filter(
    (key) =>
      !ordered.includes(key) &&
      !CONTEXT_KEYS.has(key) &&
      (["string", "integer", "boolean", "array"].includes(String(schemaOf(definition, key).type)) ||
        (key === "filters" && schemaOf(definition, key).type === "object")),
  );
  return [...ordered, ...additional];
}

/** A compact DS-CMP-21 select of the one-row toolbar (RV-08). */
function ChoiceField({
  name,
  label,
  options,
  value,
  error,
  disabled,
  onChange,
}: {
  readonly name: string;
  readonly label: string;
  readonly options: readonly { readonly value: string; readonly label: string }[];
  readonly value: string | null;
  readonly error: string | undefined;
  readonly disabled: boolean;
  readonly onChange: (value: string) => void;
}) {
  return (
    <Field name={name} label={label} error={error} width="period">
      {(control) => (
        <Select
          control={control}
          options={options}
          value={value}
          onChange={onChange}
          invalid={error !== undefined}
          disabled={disabled}
        />
      )}
    </Field>
  );
}

export function DateParameter({
  name,
  label,
  value,
  error,
  disabled = false,
  onChange,
}: {
  readonly name: string;
  readonly label: string;
  readonly value: string;
  readonly error: string | undefined;
  readonly disabled?: boolean;
  readonly onChange: (value: string) => void;
}) {
  const [text, setText] = useState(value === "" ? "" : formatDate(value));
  const [formatError, setFormatError] = useState<string | null>(null);
  return (
    <Field name={name} label={label} error={error ?? formatError} width="date">
      {(control) => (
        <DateInput
          control={control}
          value={text}
          onChange={setText}
          onValue={(date) => onChange(date ?? "")}
          onFormatError={setFormatError}
          invalid={error !== undefined || formatError !== null}
          disabled={disabled}
        />
      )}
    </Field>
  );
}

export interface ParametersToolbarProps {
  readonly definition: ReportDefinition;
  readonly context: ReportContext;
  /** The `p.<key>` values over the §5.6 defaults. */
  readonly values: Readonly<Record<string, string>>;
  readonly errors: Readonly<Record<string, string>>;
  /** The resolved POL-201 bands of the run on screen, for example "12, 24 months". */
  readonly timeBands: string | null;
  readonly onChange: (key: string, value: string) => void;
  readonly onRun: () => void;
  /** The screen's field order when it differs from §5.6 (SF-04 wireframe: Rows first). */
  readonly keys?: readonly string[] | undefined;
  /** Screen controls placed before "Run report", for example SF-04 "Layout". */
  readonly children?: ReactNode;
  /** The SF id of the host screen: `<SF id>-filter-bar`. */
  readonly testIdPrefix?: string | undefined;
  /**
   * Why the fields take no input, where they take none (RV-04 rev 1.98: the source is a lock): they
   * are shown disabled and the sentence stands under them.
   */
  readonly unavailable?: string | undefined;
}

/** The keys that render a field the reader can set: `time_bands` is a figure with its tooltip. */
function isField(definition: ReportDefinition, key: string): boolean {
  if (key === "time_bands") {
    return false;
  }
  return key === "granularity" || key === "measure" ? enumOf(definition, key).length >= 2 : true;
}

export function ParametersToolbar({
  definition,
  context,
  values,
  errors,
  timeBands,
  onChange,
  onRun,
  keys: screenKeys,
  children,
  testIdPrefix = "SF-08",
  unavailable,
}: ParametersToolbarProps) {
  const noteId = useId();
  const available = new Set(toolbarKeys(definition));
  const keys = screenKeys?.filter((key) => available.has(key)) ?? toolbarKeys(definition);
  const disabled = unavailable !== undefined;
  const noted = disabled && keys.some((key) => isField(definition, key));
  const periodOptions = context.periods.map((item) => ({
    value: item.period.period_key,
    label: periodLabel(item.period),
  }));
  const label = (key: string) => {
    const message = `reports.parameters.${key}`;
    if (hasMessage(message)) return t(message);
    const title = schemaOf(definition, key).title;
    return typeof title === "string"
      ? title
      : key
          .split("_")
          .map((word, index) =>
            word === "id"
              ? "ID"
              : word === "ids"
                ? "IDs"
                : index === 0
                  ? word[0]?.toUpperCase() + word.slice(1)
                  : word,
          )
          .join(" ");
  };
  const choiceLabel = (key: string, value: string) =>
    key === "currency_view"
      ? t(`reports.parameters.currencyView.${value}`)
      : hasMessage(`reports.parameters.${key}.${value}`)
        ? t(`reports.parameters.${key}.${value}`)
        : value;

  const toolbar = (
    <div
      role="toolbar"
      aria-label={t("reports.parameters.label")}
      aria-describedby={noted ? noteId : undefined}
      data-testid={`${testIdPrefix}-filter-bar`}
      className="flex flex-wrap items-end gap-3"
    >
      {context.entity === null && values.entity_codes && (
        <div className="flex items-center gap-2">
          <p>{t("reports.parameters.savedEntities", { entities: values.entity_codes })}</p>
          <Button
            variant="secondary"
            disabledReason={unavailable}
            onClick={() => onChange("entity_codes", "")}
          >
            {t("reports.parameters.useAllEntities")}
          </Button>
        </div>
      )}
      {keys.map((key) => {
        const value = values[key] ?? "";
        const error = errors[key];
        if (
          definition.code === "variance_between_closes" &&
          (key === "from_period_lock_id" || key === "to_period_lock_id")
        ) {
          return (
            <CloseLockParameter
              key={key}
              name={key}
              context={context}
              value={value}
              error={error}
              disabled={disabled}
              onChange={(next) => onChange(key, next)}
            />
          );
        }
        switch (key) {
          case "migration_id":
            return (
              <MigrationParameter
                key={key}
                value={value}
                error={error}
                disabled={disabled}
                onChange={(next) => onChange(key, next)}
              />
            );
          case "filters":
            return (
              <div key={key}>
                <ReportFilters
                  value={value}
                  disabled={disabled}
                  onChange={(next) => onChange(key, next)}
                />
                {error && <p role="alert">{error}</p>}
              </div>
            );
          case "from_period_key":
          case "to_period_key":
            return (
              <ChoiceField
                key={key}
                name={`p-${key}`}
                label={label(key)}
                options={periodOptions}
                value={value === "" ? null : value}
                onChange={(next) => onChange(key, next)}
                error={error}
                disabled={disabled}
              />
            );
          case "from_date":
          case "to_date":
            return (
              <DateParameter
                key={`${key}:${value}`}
                name={`p-${key}`}
                label={label(key)}
                value={value}
                error={error}
                disabled={disabled}
                onChange={(next) => onChange(key, next)}
              />
            );
          case "mode":
          case "granularity":
          case "measure": {
            const options = enumOf(definition, key).map((item) => ({
              value: item,
              label: choiceLabel(key, item),
              disabledReason: unavailable,
            }));
            return options.length < 2 ? null : (
              <SegmentedControl
                key={key}
                label={label(key)}
                options={options}
                value={value === "" ? (options[0]?.value ?? "") : value}
                onChange={(next) => onChange(key, next)}
              />
            );
          }
          case "row_dimension":
            return (
              <ChoiceField
                key={key}
                name={`p-${key}`}
                label={label(key)}
                options={enumOf(definition, key).map((item) => ({
                  value: item,
                  label: choiceLabel(key, item),
                }))}
                value={value === "" ? (enumOf(definition, key)[0] ?? null) : value}
                onChange={(next) => onChange(key, next)}
                error={error}
                disabled={disabled}
              />
            );
          case "time_bands":
            return (
              <div key={key} className="flex flex-col gap-1">
                <span className="text-body-sm font-medium text-fg-1">{label(key)}</span>
                <Tooltip content={t("reports.parameters.timeBandsHelp")}>
                  {(trigger) => (
                    <span
                      {...trigger}
                      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- DS-CMP-27: a tooltip trigger is focusable
                      tabIndex={0}
                      className="text-body-sm text-fg-2"
                    >
                      {timeBands ?? NO_VALUE}
                    </span>
                  )}
                </Tooltip>
              </div>
            );
          case "currency_view":
            return (
              <ChoiceField
                key={key}
                name="p-currency_view"
                label={label(key)}
                options={CURRENCY_VIEWS.map((item) => ({
                  value: item,
                  label: choiceLabel(key, item),
                }))}
                value={value === "" ? "transaction" : value}
                onChange={(next) => onChange(key, next)}
                error={error}
                disabled={disabled && !supportsLockedCurrency(definition)}
              />
            );
          default: {
            const schema = schemaOf(definition, key);
            const required =
              Array.isArray(definition.parameters_schema.required) &&
              definition.parameters_schema.required.includes(key);
            if (schema.format === "date")
              return (
                <DateParameter
                  key={`${key}:${value}`}
                  name={`p-${key}`}
                  label={label(key)}
                  value={value}
                  error={error}
                  disabled={disabled}
                  onChange={(next) => onChange(key, next)}
                />
              );
            if (schema.type === "boolean" || enumOf(definition, key).length > 0) {
              const options =
                schema.type === "boolean"
                  ? [
                      { value: "true", label: t("common.grid.yes") },
                      { value: "false", label: t("common.grid.no") },
                    ]
                  : enumOf(definition, key).map((item) => ({ value: item, label: item }));
              return (
                <ChoiceField
                  key={key}
                  name={`p-${key}`}
                  label={label(key)}
                  options={options}
                  value={value || null}
                  error={error}
                  disabled={disabled}
                  onChange={(next) => onChange(key, next)}
                />
              );
            }
            return (
              <TextField
                key={key}
                name={`p-${key}`}
                label={label(key)}
                optional={!required}
                required={required}
                help={schema.type === "array" ? t("reports.parameters.listHelp") : undefined}
                inputMode={schema.type === "integer" ? "numeric" : "text"}
                width="money"
                value={value}
                onChange={(next) => onChange(key, next)}
                error={error}
                disabled={disabled}
              />
            );
          }
        }
      })}
      {children}
      <Button
        variant="primary"
        onClick={onRun}
        disabledReason={
          !disabled &&
          keys.includes("filters") &&
          !validFilterRows(filterRows(values.filters ?? ""))
            ? t("reports.filters.invalid")
            : undefined
        }
      >
        {t("reports.parameters.run")}
      </Button>
    </div>
  );
  return noted ? (
    <>
      {toolbar}
      <p id={noteId} className="text-body-sm text-fg-2">
        {supportsLockedCurrency(definition)
          ? t("reports.asLocked.currencyParameters")
          : unavailable}
      </p>
    </>
  ) : (
    toolbar
  );
}
