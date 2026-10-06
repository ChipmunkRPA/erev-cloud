// Filter chip editors (DESIGN_SYSTEM DS-CMP-13 "Editors by field type"): enum checkbox list with search;
// text contains or equals; money and number is, between, at least, at most with string decimal
// validation; date presets and a custom range; period picker; user combobox; boolean Yes or No. Apply
// reports an invalid value inline and keeps the popover open.
import { type FormEvent, useId, useState } from "react";

import { formatDate, parseDateInput, parseMoneyInput } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { Combobox } from "../form/Combobox";
import { DateInput } from "../form/DateInput";
import { controlClass, Field } from "../form/Field";
import { PeriodInput } from "../form/PeriodInput";
import { WarningCircle } from "../icons/registry";
import { Button } from "../ui/Button";
import type { Filter, FilterField, FilterOperator } from "./filters";
import { operatorLabel } from "./filters";

type Condition = Exclude<FilterOperator, "in">;

/** Enum lists longer than this get a search input. */
export const VALUE_SEARCH_THRESHOLD = 7;
const CUSTOM_RANGE = "custom";
const NUMBER = /^-?\d+(\.\d+)?$/;

function conditionsOf(field: FilterField): readonly Condition[] {
  const conditions: Condition[] = [];
  for (const operator of field.operators) {
    const condition = operator === "in" ? "is" : operator;
    if (!conditions.includes(condition)) {
      conditions.push(condition);
    }
  }
  return conditions;
}

function initialTexts(field: FilterField, filter: Filter | null): readonly [string, string] {
  const values = filter?.values ?? [];
  const text = (value: string | undefined) =>
    value === undefined ? "" : field.kind === "date" ? formatDate(value) : value;
  return [text(values[0]), text(values[1])];
}

function initialPreset(field: FilterField, filter: Filter | null): string {
  const presets = field.presets ?? [];
  if (filter === null) {
    return presets[0]?.label ?? CUSTOM_RANGE;
  }
  const [from, to] = filter.values;
  return presets.find((preset) => preset.from === from && preset.to === to)?.label ?? CUSTOM_RANGE;
}

export interface FilterEditorProps {
  readonly field: FilterField;
  readonly initial: Filter | null;
  readonly onApply: (filter: Filter) => void;
}

export function FilterEditor({ field, initial, onApply }: FilterEditorProps) {
  const base = useId();
  const conditions = conditionsOf(field);
  const [condition, setCondition] = useState<Condition>(() => {
    if (initial === null) {
      return conditions[0] ?? "is";
    }
    return initial.operator === "in" ? "is" : initial.operator;
  });
  const [selected, setSelected] = useState<readonly string[]>(initial?.values ?? []);
  const [texts, setTexts] = useState(() => initialTexts(field, initial));
  const [preset, setPreset] = useState(() => initialPreset(field, initial));
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const invalid = error !== null;

  const setText = (index: 0 | 1, text: string) => {
    setTexts((current) => (index === 0 ? [text, current[1]] : [current[0], text]));
    setError(null);
  };

  const number = (text: string): string | null => {
    const typed = text.trim();
    if (field.kind === "money" && field.currency !== undefined) {
      const parsed = parseMoneyInput(typed, field.currency);
      return parsed.ok ? parsed.value : null;
    }
    const plain = typed.replace(/[\s,]/g, "");
    return NUMBER.test(plain) ? plain : null;
  };

  const build = (): Filter | string => {
    const name = field.name;
    if (condition === "empty" || condition === "notempty") {
      return { field: name, operator: condition, values: [] };
    }
    switch (field.kind) {
      case "enum": {
        if (selected.length === 0) {
          return t("common.filters.chooseValue");
        }
        const order = (field.options ?? []).map((option) => option.value);
        const values = [...selected].sort((a, b) => order.indexOf(a) - order.indexOf(b));
        // "is" stands for `in` too (conditionsOf): several values, or a field that offers only `in`,
        // are written as `in`, so the chip always carries an operator of the field (SCR-URL-10).
        const several = values.length > 1 || !field.operators.includes("is");
        const operator = condition === "is" && several ? "in" : condition;
        return { field: name, operator, values };
      }
      case "boolean":
      case "period":
      case "user": {
        const value = selected[0];
        return value === undefined
          ? t("common.filters.enterValue")
          : { field: name, operator: condition, values: [value] };
      }
      case "text": {
        const value = texts[0].trim();
        return value === ""
          ? t("common.filters.enterValue")
          : { field: name, operator: condition, values: [value] };
      }
      case "money":
      case "number": {
        const needed = condition === "between" ? 2 : 1;
        const typed = texts.slice(0, needed);
        if (typed.some((text) => text.trim() === "")) {
          return t(needed === 2 ? "common.filters.bothValues" : "common.filters.enterValue");
        }
        const values = typed.map(number);
        if (values.some((value) => value === null)) {
          return t("common.filters.numberInvalid");
        }
        return { field: name, operator: condition, values: values as string[] };
      }
      case "date": {
        if (condition === "between" && preset !== CUSTOM_RANGE) {
          const chosen = (field.presets ?? []).find((item) => item.label === preset);
          return chosen === undefined
            ? t("common.filters.enterValue")
            : { field: name, operator: "between", values: [chosen.from, chosen.to] };
        }
        const needed = condition === "between" ? 2 : 1;
        const dates = texts.slice(0, needed).map((text) => parseDateInput(text));
        if (texts.slice(0, needed).some((text) => text.trim() === "")) {
          return t(needed === 2 ? "common.filters.bothValues" : "common.filters.enterValue");
        }
        const values = dates.map((date) => (date.ok ? date.value : null));
        if (values.some((value) => value === null)) {
          return t("common.form.date.invalid");
        }
        const [from = "", to = ""] = values as string[];
        if (needed === 2 && from > to) {
          return t("common.filters.rangeOrder");
        }
        return { field: name, operator: condition, values: values as string[] };
      }
    }
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const result = build();
    if (typeof result === "string") {
      setError(result);
    } else {
      onApply(result);
    }
  };

  const radios = (
    name: string,
    legend: string,
    items: readonly { readonly value: string; readonly label: string }[],
    value: string,
    onPick: (value: string) => void,
    hideLegend = false,
  ) => (
    <fieldset className="flex flex-col gap-1">
      <legend className={hideLegend ? "sr-only" : "mb-1 text-body-sm font-medium text-fg-1"}>
        {legend}
      </legend>
      {items.map((item) => (
        <label key={item.value} className="flex items-center gap-2 text-body-sm text-fg-1">
          <input
            type="radio"
            name={`${base}-${name}`}
            value={item.value}
            checked={value === item.value}
            onChange={() => {
              onPick(item.value);
              setError(null);
            }}
          />
          {item.label}
        </label>
      ))}
    </fieldset>
  );

  const textField = (index: 0 | 1, label: string, kind: "text" | "decimal") => (
    <Field name={`filter-${String(index)}`} label={label} error={index === 0 ? error : null}>
      {(control) => (
        <input
          {...control}
          type="text"
          inputMode={kind === "decimal" ? "decimal" : undefined}
          autoComplete="off"
          value={texts[index]}
          onChange={(event) => setText(index, event.target.value)}
          className={controlClass(invalid)}
        />
      )}
    </Field>
  );

  const dateField = (index: 0 | 1, label: string) => (
    <Field name={`filter-date-${String(index)}`} label={label} error={index === 0 ? error : null}>
      {(control) => (
        <DateInput
          control={control}
          value={texts[index]}
          onChange={(text) => setText(index, text)}
          invalid={invalid}
        />
      )}
    </Field>
  );

  let values = null;
  let inlineError = false;
  if (condition !== "empty" && condition !== "notempty") {
    switch (field.kind) {
      case "enum": {
        inlineError = true;
        const options = field.options ?? [];
        const query = search.trim().toLocaleLowerCase();
        const shown =
          query === ""
            ? options
            : options.filter((option) => option.label.toLocaleLowerCase().includes(query));
        const multiple = condition === "not" || field.operators.includes("in");
        values = (
          <fieldset className="flex flex-col gap-2">
            <legend className="sr-only">{field.label}</legend>
            {options.length > VALUE_SEARCH_THRESHOLD ? (
              <input
                type="search"
                aria-label={t("common.filters.searchValues")}
                placeholder={t("common.filters.searchValues")}
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                className={controlClass(false)}
              />
            ) : null}
            <div className="flex max-h-60 flex-col gap-1 overflow-y-auto">
              {shown.map((option) => (
                <label
                  key={option.value}
                  className="flex min-h-[var(--row-h)] items-center gap-2 text-body-sm text-fg-1"
                >
                  <input
                    type="checkbox"
                    checked={selected.includes(option.value)}
                    onChange={() => {
                      setError(null);
                      setSelected((current) => {
                        if (current.includes(option.value)) {
                          return current.filter((value) => value !== option.value);
                        }
                        return multiple ? [...current, option.value] : [option.value];
                      });
                    }}
                  />
                  {option.label}
                </label>
              ))}
            </div>
            {field.optionsLoading === true ? (
              <p role="status" className="text-body-sm text-fg-3">
                {t("common.filters.loadingOptions")}
              </p>
            ) : null}
          </fieldset>
        );
        break;
      }
      case "boolean":
        inlineError = true;
        values = radios(
          "boolean",
          field.label,
          [
            { value: "true", label: t("common.filters.yes") },
            { value: "false", label: t("common.filters.no") },
          ],
          selected[0] ?? "",
          (value) => setSelected([value]),
          true,
        );
        break;
      case "text":
        values = textField(0, t("common.filters.value"), "text");
        break;
      case "money":
      case "number":
        values =
          condition === "between" ? (
            <div className="flex flex-col gap-2">
              {textField(0, t("common.filters.from"), "decimal")}
              {textField(1, t("common.filters.to"), "decimal")}
            </div>
          ) : (
            textField(0, t("common.filters.value"), "decimal")
          );
        break;
      case "date":
        if (condition === "between") {
          inlineError = preset !== CUSTOM_RANGE;
          values = (
            <div className="flex flex-col gap-2">
              {radios(
                "preset",
                t("common.filters.range"),
                [
                  ...(field.presets ?? []).map((item) => ({
                    value: item.label,
                    label: item.label,
                  })),
                  { value: CUSTOM_RANGE, label: t("common.filters.customRange") },
                ],
                preset,
                setPreset,
              )}
              {preset === CUSTOM_RANGE ? (
                <>
                  {dateField(0, t("common.filters.from"))}
                  {dateField(1, t("common.filters.to"))}
                </>
              ) : null}
            </div>
          );
        } else {
          values = dateField(0, t("common.filters.value"));
        }
        break;
      case "period":
        values = (
          <Field name="filter-period" label={field.label} error={error}>
            {(control) => (
              <PeriodInput
                control={control}
                periods={field.periods ?? []}
                value={selected[0] ?? null}
                onChange={(key) => {
                  setSelected([key]);
                  setError(null);
                }}
                invalid={invalid}
              />
            )}
          </Field>
        );
        break;
      case "user":
        values = (
          <Field name="filter-user" label={field.label} error={error}>
            {(control) => (
              <Combobox
                control={control}
                options={field.options ?? []}
                value={selected[0] ?? null}
                onChange={(value) => {
                  setSelected(value === null ? [] : [value]);
                  setError(null);
                }}
                invalid={invalid}
              />
            )}
          </Field>
        );
        break;
    }
  } else {
    inlineError = true;
  }

  return (
    <form noValidate onSubmit={onSubmit} className="flex w-72 flex-col gap-3 p-3">
      {conditions.length > 1
        ? radios(
            "condition",
            t("common.filters.condition"),
            conditions.map((item) => ({ value: item, label: operatorLabel(field.kind, item) })),
            condition,
            (value) => setCondition(value as Condition),
          )
        : null}
      {values}
      {inlineError && error !== null ? (
        <p role="alert" className="flex items-start gap-1 text-body-sm text-negative-fg">
          <WarningCircle aria-hidden="true" className="mt-0.5 shrink-0" />
          {error}
        </p>
      ) : null}
      <div className="flex justify-end">
        <Button type="submit" variant="primary" size="sm">
          {t("common.filters.apply")}
        </Button>
      </div>
    </form>
  );
}
