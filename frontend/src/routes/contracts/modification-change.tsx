// SF-07 step 1 "Change" (SCREENS §7.4; DESIGN_SYSTEM DS-CMP-10 form-held lines, DS-CMP-21; 04 API-R-31,
// §16.14 API-S-Modification; ENGINE_SPEC S06-R-19; PRD BR-MOD-04; docs/dev-guide.md DG-FE-06, DG-FE-07;
// BUILD_SPEC CTR-27). Two forms answer one API-S-Modification body through `lib/forms/modification`:
// - the general modification: kind, reference, effective date, scope description and the lines in the
//   line editor, or the one price change of kind "Price change";
// - a subscription change (`?action=`): the obligation, the quantity and the price of one line that has
//   the shape of its kind. `POST /contracts/{id}/subscription-changes` is not on main (CTR-18), so the
//   action is an ordinary modification of the matching kind.
// The form is submitted by the wizard's "Next" (`formId`); a `validation-failed` answer lands on the
// fields and the cells it names.
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import { Banner } from "../../components/feedback/Banner";
import { DateInput } from "../../components/form/DateInput";
import { ErrorSummary, type FormErrorEntry } from "../../components/form/ErrorSummary";
import { Field, fieldId } from "../../components/form/Field";
import { MoneyInput } from "../../components/form/MoneyInput";
import { Select } from "../../components/form/Select";
import {
  type LineCellKind,
  type LineColumn,
  LineEditor,
} from "../../components/line-editor/LineEditor";
import type { ApiProblem } from "../../lib/api/problems";
import { currencyRegistered } from "../../lib/api/queries/approvals";
import type { ContractEvent } from "../../lib/api/queries/contracts";
import {
  type ModificationCreateBody,
  type ModificationKind,
  MODIFICATION_KINDS,
} from "../../lib/api/queries/modifications";
import { dateOf, MAX_LINES } from "../../lib/forms/contract";
import {
  ADDING_ACTIONS,
  buildChange,
  buildSubscription,
  CHANGE_COLUMNS,
  CHANGE_LINES_FIELD,
  type ChangeColumn,
  type ChangeContext,
  type ChangeForm,
  type ChangeLine,
  changeLineField,
  changeLinePatch,
  changeLineValue,
  emptyChangeLine,
  LINE_ACTIONS,
  PRICE_CHANGE,
  RENEWING_ACTIONS,
  type SubscriptionForm,
} from "../../lib/forms/modification";
import { formatDate, formatNumber } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { TextField } from "./drawers/common";

export interface Choice {
  readonly value: string;
  readonly label: string;
}

export type ChangeVariant =
  | { readonly kind: "general"; readonly initial: ChangeForm }
  | { readonly kind: "subscription"; readonly initial: SubscriptionForm };

export interface ChangeStepProps {
  /** The id of the form element: the wizard's "Next" submits it. */
  readonly formId: string;
  readonly variant: ChangeVariant;
  readonly context: ChangeContext;
  /** Obligation key → "<key> · <product code> · <date range>" for the selects. */
  readonly obligationChoices: readonly Choice[];
  readonly products: readonly Choice[];
  readonly entities: readonly Choice[];
  /** The event of the contract with the latest effective date, for the BR-MOD-04 note; null when unknown. */
  readonly latestEvent: ContractEvent | null;
  /** The answer of the last save, when it was refused. */
  readonly problem: ApiProblem | null;
  readonly busy: boolean;
  readonly onDirty: (dirty: boolean) => void;
  /** The form is valid: the body of `POST …/modifications` or of the `PATCH` of a draft. */
  readonly onBuilt: (body: ModificationCreateBody) => void;
}

const COLUMN_KIND: Readonly<Record<ChangeColumn, LineCellKind>> = {
  action: "select",
  obligationKey: "text",
  product: "combobox",
  quantityChange: "decimal",
  considerationChange: "money",
  startDate: "date",
  endDate: "date",
  performingEntity: "select",
  sspVersion: "text",
  memo1: "text",
  memo2: "text",
  memo3: "text",
};

const COLUMN_WIDTH: Readonly<Record<ChangeColumn, string>> = {
  action: "w-32 min-w-32",
  obligationKey: "w-32 min-w-32",
  product: "w-72 min-w-72",
  quantityChange: "w-32 min-w-32",
  considerationChange: "w-48 min-w-48",
  startDate: "w-36 min-w-36",
  endDate: "w-36 min-w-36",
  performingEntity: "w-56 min-w-56",
  sspVersion: "w-40 min-w-40",
  memo1: "w-48 min-w-48",
  memo2: "w-48 min-w-48",
  memo3: "w-48 min-w-48",
};

/** API-S-Modification member of a line → grid column (general form). */
const LINE_MEMBER: Readonly<Record<string, ChangeColumn>> = {
  action: "action",
  obligation_key: "obligationKey",
  product_code: "product",
  quantity_delta: "quantityChange",
  consideration_delta: "considerationChange",
  start_date: "startDate",
  end_date: "endDate",
  selling_entity_code: "performingEntity",
  ssp_version_label: "sspVersion",
  memo_1: "memo1",
  memo_2: "memo2",
  memo_3: "memo3",
};

/** API-S-Modification member of the one line → field of the subscription form. */
const SUBSCRIPTION_MEMBER: Readonly<Record<string, string>> = {
  obligation_key: "obligationKey",
  product_code: "obligationKey",
  quantity_delta: "quantity",
  consideration_delta: "price",
  start_date: "effectiveDate",
  end_date: "endDate",
};

const HEADER_MEMBER: Readonly<Record<string, string>> = {
  kind: "kind",
  reference: "reference",
  effective_date: "effectiveDate",
  rationale: "rationale",
  price_change_amount: "priceChangeAmount",
  lines: CHANGE_LINES_FIELD,
};

// `lines[0].obligation_key`, `lines[0].consideration_delta.currency`, `lines[0]` (04 API-C-05).
const LINE_POINTER = /^lines\[(\d+)\](?:\.([a-z_0-9]+))?/;

interface Placed {
  readonly fields: Readonly<Record<string, string>>;
  readonly unplaced: readonly string[];
}

/** The `errors[]` of a refused save on the fields and cells they name; the rest goes to the banner. */
export function placeChangeProblem(problem: ApiProblem, lineIds: readonly string[] | null): Placed {
  const fields: Record<string, string> = {};
  const unplaced: string[] = [];
  for (const error of problem.errors) {
    const pointer = error.field ?? "";
    const line = LINE_POINTER.exec(pointer);
    let name: string | null = null;
    if (line !== null) {
      const member = line[2];
      if (lineIds === null) {
        name = member === undefined ? null : (SUBSCRIPTION_MEMBER[member] ?? null);
      } else {
        const id = lineIds[Number(line[1])];
        const column = member === undefined ? "obligationKey" : LINE_MEMBER[member];
        name = id === undefined || column === undefined ? null : changeLineField(id, column);
      }
    } else {
      name = HEADER_MEMBER[pointer] ?? null;
    }
    if (name === null || name in fields) {
      unplaced.push(error.message);
    } else {
      fields[name] = error.message;
    }
  }
  return { fields, unplaced };
}

function without(
  record: Readonly<Record<string, string>>,
  names: readonly string[],
): Readonly<Record<string, string>> {
  return names.some((name) => name in record)
    ? Object.fromEntries(Object.entries(record).filter(([name]) => !names.includes(name)))
    : record;
}

interface FormShellProps {
  readonly formId: string;
  readonly busy: boolean;
  readonly problem: ApiProblem | null;
  readonly unplaced: readonly string[];
  readonly entries: readonly FormErrorEntry[];
  readonly focusTick: number;
  readonly onSubmit: () => void;
  readonly children: ReactNode;
}

function FormShell({
  formId,
  busy,
  problem,
  unplaced,
  entries,
  focusTick,
  onSubmit,
  children,
}: FormShellProps) {
  return (
    <form
      id={formId}
      noValidate
      aria-busy={busy ? true : undefined}
      className="flex flex-col gap-6"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      {problem === null ? null : (
        <Banner tone="negative" title={problem.title} announce="live" headingLevel={3}>
          {problem.detail === null ? null : <p>{problem.detail}</p>}
          {unplaced.map((message) => (
            <p key={message}>{message}</p>
          ))}
          {problem.requestId === null ? null : (
            <p>{t("contracts.drawer.reference", { reference: problem.requestId })}</p>
          )}
        </Banner>
      )}
      <ErrorSummary errors={entries} submitCount={focusTick} />
      {children}
    </form>
  );
}

/** Focus follows a failed submit to the one wrong field; two or more go to the error summary. */
function useErrorFocus(entries: readonly FormErrorEntry[], focusTick: number): void {
  const only = entries.length === 1 ? (entries[0]?.name ?? null) : null;
  useEffect(() => {
    if (focusTick > 0 && only !== null) {
      document.getElementById(fieldId(only))?.focus();
    }
    // Focus follows a submit, not every change of the errors.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusTick]);
}

function BackdatedNote({
  effectiveDate,
  latestEvent,
}: {
  readonly effectiveDate: string;
  readonly latestEvent: ContractEvent | null;
}) {
  const effective = dateOf(effectiveDate);
  if (effective === null || latestEvent === null || effective >= latestEvent.effective_date) {
    return null;
  }
  // BR-MOD-04: a backdated modification is allowed; the note says what replays.
  return (
    <p className="text-body-sm text-fg-2">
      {t("modifications.wizard.change.backdated", {
        date: formatDate(effective),
        latest: formatDate(latestEvent.effective_date),
      })}
    </p>
  );
}

const GENERAL_FIELDS = [
  "kind",
  "reference",
  "effectiveDate",
  "rationale",
  "priceObligationKey",
  "priceChangeAmount",
  CHANGE_LINES_FIELD,
] as const;

/**
 * The name of the scope description's control. A field's id is made from its name
 * (`components/form/Field`), and the estimate version drawer that "Add estimate version" opens over
 * this form has a field `rationale` of its own (SCREENS §7.4): under one id the drawer's label and its
 * error link would reach this control.
 */
const SCOPE_CONTROL = "scope_description";

/** A field of the general form → the name of its control. */
function controlOf(field: string): string {
  return field === "rationale" ? SCOPE_CONTROL : field;
}

function lineColumns(
  context: ChangeContext,
  products: readonly Choice[],
  entities: readonly Choice[],
): readonly LineColumn<ChangeLine>[] {
  const money = currencyRegistered(context.currency) ? context.currency : null;
  const options: Partial<Record<ChangeColumn, readonly Choice[]>> = {
    action: LINE_ACTIONS.map((action) => ({
      value: action,
      label: t(`modifications.wizard.change.action.${action}`),
    })),
    product: products,
    performingEntity: entities,
  };
  return CHANGE_COLUMNS.map((column) => {
    const label = t(`modifications.wizard.change.column.${column}`);
    const kind = COLUMN_KIND[column];
    return {
      id: column,
      header:
        kind === "money" && money !== null
          ? t("modifications.wizard.change.column.considerationChangeIn", { currency: money })
          : label,
      label,
      kind,
      value: (line) => changeLineValue(line, column),
      options: options[column],
      currency: kind === "money" ? money : undefined,
      // SCREENS §7.4: only an added line names the product of its new obligation.
      disabled: column === "product" ? (line) => line.action !== "ADD" : undefined,
      rowHeader: column === "obligationKey",
      width: COLUMN_WIDTH[column],
    };
  });
}

function GeneralForm({
  formId,
  initial,
  context,
  obligationChoices,
  products,
  entities,
  latestEvent,
  problem,
  busy,
  onDirty,
  onBuilt,
}: Omit<ChangeStepProps, "variant"> & { readonly initial: ChangeForm }) {
  const [form, setForm] = useState(initial);
  const [attempted, setAttempted] = useState(false);
  const [focusTick, setFocusTick] = useState(0);
  const [formatErrors, setFormatErrors] = useState<Readonly<Record<string, string>>>({});
  const [cleared, setCleared] = useState<readonly string[]>([]);
  const lineIds = useRef(initial.lines.length);
  const pendingFocus = useRef<string | null>(null);

  const built = useMemo(() => buildChange(form, context), [form, context]);
  const columns = useMemo(
    () => lineColumns(context, products, entities),
    [context, products, entities],
  );
  // The server names lines by position: the placement is of the lines that were sent.
  const sentIds = useRef<readonly string[]>([]);
  const placed = useMemo(
    () => (problem === null ? null : placeChangeProblem(problem, sentIds.current)),
    [problem],
  );
  useEffect(() => setCleared([]), [problem]);
  const serverFields = placed === null ? {} : without(placed.fields, cleared);
  const errors: Readonly<Record<string, string>> = {
    ...formatErrors,
    ...serverFields,
    ...(attempted ? built.errors : {}),
  };
  const entries: FormErrorEntry[] = [
    ...GENERAL_FIELDS.flatMap((name) =>
      name in errors ? [{ name: controlOf(name), message: errors[name] ?? "" }] : [],
    ),
    ...form.lines.flatMap((line, index) =>
      CHANGE_COLUMNS.flatMap((column) => {
        const name = changeLineField(line.id, column);
        return name in errors
          ? [
              {
                name,
                message: t("contracts.draft.error.inLine", {
                  line: formatNumber(index + 1, { kind: "count" }),
                  message: errors[name] ?? "",
                }),
              },
            ]
          : [];
      }),
    ),
  ];
  useErrorFocus(entries, focusTick);
  useEffect(() => {
    if (pendingFocus.current !== null) {
      document.getElementById(pendingFocus.current)?.focus();
      pendingFocus.current = null;
    }
  });
  const dirty = JSON.stringify(form) !== JSON.stringify(initial);
  useEffect(() => onDirty(dirty), [dirty, onDirty]);

  const set = <K extends keyof ChangeForm>(name: K, value: ChangeForm[K]) => {
    setForm((current) => ({ ...current, [name]: value }));
    setCleared((current) => [...current, name]);
  };
  const setFormatError = (name: string, message: string | null) =>
    setFormatErrors((current) =>
      message === null ? without(current, [name]) : { ...current, [name]: message },
    );
  const changeLine = (lineId: string, columnId: string, value: string) => {
    const column = CHANGE_COLUMNS.find((candidate) => candidate === columnId);
    if (column === undefined) {
      return;
    }
    setForm((current) => ({
      ...current,
      lines: current.lines.map((line) =>
        line.id === lineId ? { ...line, ...changeLinePatch(column, value) } : line,
      ),
    }));
    setCleared((current) => [
      ...current,
      changeLineField(lineId, column),
      ...(column === "action" ? [changeLineField(lineId, "product")] : []),
    ]);
  };
  const addLine = () => {
    lineIds.current += 1;
    const id = `l${String(lineIds.current)}`;
    setForm((current) => ({ ...current, lines: [...current.lines, emptyChangeLine(id)] }));
    pendingFocus.current = fieldId(changeLineField(id, "action"));
  };
  const removeLine = (lineId: string) => {
    const index = form.lines.findIndex((line) => line.id === lineId);
    const neighbour = form.lines[index + 1] ?? form.lines[index - 1];
    pendingFocus.current =
      neighbour === undefined
        ? fieldId(CHANGE_LINES_FIELD)
        : fieldId(changeLineField(neighbour.id, "action"));
    setForm((current) => ({
      ...current,
      lines: current.lines.filter((line) => line.id !== lineId),
    }));
    setFormatErrors((current) =>
      without(
        current,
        CHANGE_COLUMNS.map((column) => changeLineField(lineId, column)),
      ),
    );
    // The pointers of the server name rows by position, which a removal moves.
    setCleared((current) => [...current, ...Object.keys(placed?.fields ?? {})]);
  };
  const submit = () => {
    setAttempted(true);
    if (built.body === null) {
      setFocusTick((tick) => tick + 1);
      return;
    }
    sentIds.current = form.lines.map((line) => line.id);
    onBuilt(built.body);
  };
  useEffect(() => {
    if (problem !== null) {
      setFocusTick((tick) => tick + 1);
    }
  }, [problem]);

  const shown = (name: string) => errors[name] ?? null;
  const priceChange = form.kind === PRICE_CHANGE;
  const kinds = MODIFICATION_KINDS.map((kind) => ({
    value: kind,
    label: t(`modification.kind.${kind}`),
  }));

  return (
    <FormShell
      formId={formId}
      busy={busy}
      problem={problem}
      unplaced={placed?.unplaced ?? []}
      entries={entries}
      focusTick={focusTick}
      onSubmit={submit}
    >
      <div inert={busy} className="flex w-full max-w-[var(--content-max-form)] flex-col gap-4">
        <Field
          name="kind"
          label={t("modifications.wizard.change.kind")}
          required
          error={shown("kind")}
          width="text"
        >
          {(control) => (
            <Select<ModificationKind>
              control={control}
              options={kinds}
              value={form.kind}
              onChange={(value) => set("kind", value)}
              invalid={shown("kind") !== null}
            />
          )}
        </Field>
        <TextField
          name="reference"
          label={t("modifications.wizard.change.reference")}
          required
          help={t("modifications.wizard.change.referenceHelp")}
          value={form.reference}
          onChange={(value) => set("reference", value)}
          error={shown("reference")}
        />
        <Field
          name="effectiveDate"
          label={t("modifications.wizard.change.effectiveDate")}
          required
          error={shown("effectiveDate")}
          width="date"
        >
          {(control) => (
            <DateInput
              control={control}
              value={form.effectiveDate}
              onChange={(text) => set("effectiveDate", text)}
              onFormatError={(message) => setFormatError("effectiveDate", message)}
              invalid={shown("effectiveDate") !== null}
            />
          )}
        </Field>
        <BackdatedNote effectiveDate={form.effectiveDate} latestEvent={latestEvent} />
        <TextField
          name={SCOPE_CONTROL}
          label={t("modifications.wizard.change.rationale")}
          optional
          multiline
          value={form.rationale}
          onChange={(value) => set("rationale", value)}
          error={shown("rationale")}
        />
        {priceChange ? (
          <div className="flex flex-wrap gap-4">
            <Field
              name="priceObligationKey"
              label={t("modifications.wizard.change.obligation")}
              required
              error={shown("priceObligationKey")}
              width="text"
            >
              {(control) => (
                <Select<string>
                  control={control}
                  options={obligationChoices}
                  value={form.priceObligationKey}
                  onChange={(value) => set("priceObligationKey", value)}
                  invalid={shown("priceObligationKey") !== null}
                />
              )}
            </Field>
            <Field
              name="priceChangeAmount"
              label={t("modifications.wizard.change.priceChangeAmount")}
              required
              help={t("modifications.wizard.change.priceChangeHelp")}
              error={shown("priceChangeAmount")}
              width="money"
            >
              {(control) => (
                <MoneyInput
                  control={control}
                  currency={context.currency}
                  value={form.priceChangeAmount}
                  onChange={(text) => set("priceChangeAmount", text)}
                  onFormatError={(message) => setFormatError("priceChangeAmount", message)}
                  invalid={shown("priceChangeAmount") !== null}
                />
              )}
            </Field>
          </div>
        ) : null}
      </div>
      {priceChange ? null : (
        <div inert={busy}>
          <LineEditor<ChangeLine>
            title={t("modifications.wizard.change.lines.title")}
            countLabel={(count, formatted) =>
              t("contracts.draft.lines.count", { count, formatted })
            }
            columns={columns}
            rows={form.lines}
            rowId={(line) => line.id}
            name={CHANGE_LINES_FIELD}
            cellName={changeLineField}
            errors={errors}
            onChange={changeLine}
            onFormatError={setFormatError}
            addLabel={t("contracts.draft.lines.add")}
            addDisabledReason={
              form.lines.length >= MAX_LINES
                ? t("contracts.draft.lines.limit", {
                    limit: formatNumber(MAX_LINES, { kind: "count" }),
                  })
                : undefined
            }
            onAdd={addLine}
            removeLabel={(line, index) =>
              t("contracts.draft.lines.remove", {
                key:
                  line.obligationKey.trim() === ""
                    ? formatNumber(index + 1, { kind: "count" })
                    : line.obligationKey.trim(),
              })
            }
            onRemove={removeLine}
            emptyText={t("modifications.wizard.change.lines.empty")}
            testId="SF-07-grid-lines"
          />
        </div>
      )}
    </FormShell>
  );
}

const SUBSCRIPTION_FIELDS = [
  "obligationKey",
  "newKey",
  "quantity",
  "price",
  "effectiveDate",
  "endDate",
  "reference",
] as const;

function SubscriptionFormView({
  formId,
  initial,
  context,
  obligationChoices,
  latestEvent,
  problem,
  busy,
  onDirty,
  onBuilt,
}: Omit<ChangeStepProps, "variant" | "products" | "entities"> & {
  readonly initial: SubscriptionForm;
}) {
  const [form, setForm] = useState(initial);
  const [attempted, setAttempted] = useState(false);
  const [focusTick, setFocusTick] = useState(0);
  const [formatErrors, setFormatErrors] = useState<Readonly<Record<string, string>>>({});
  const [cleared, setCleared] = useState<readonly string[]>([]);

  const built = useMemo(() => buildSubscription(form, context), [form, context]);
  const placed = useMemo(
    () => (problem === null ? null : placeChangeProblem(problem, null)),
    [problem],
  );
  useEffect(() => setCleared([]), [problem]);
  const errors: Readonly<Record<string, string>> = {
    ...formatErrors,
    ...(placed === null ? {} : without(placed.fields, cleared)),
    ...(attempted ? built.errors : {}),
  };
  const entries: FormErrorEntry[] = SUBSCRIPTION_FIELDS.flatMap((name) =>
    name in errors ? [{ name, message: errors[name] ?? "" }] : [],
  );
  useErrorFocus(entries, focusTick);
  const dirty = JSON.stringify(form) !== JSON.stringify(initial);
  useEffect(() => onDirty(dirty), [dirty, onDirty]);
  useEffect(() => {
    if (problem !== null) {
      setFocusTick((tick) => tick + 1);
    }
  }, [problem]);

  const set = <K extends keyof SubscriptionForm>(name: K, value: SubscriptionForm[K]) => {
    setForm((current) => ({ ...current, [name]: value }));
    setCleared((current) => [...current, name]);
  };
  const setFormatError = (name: string, message: string | null) =>
    setFormatErrors((current) =>
      message === null ? without(current, [name]) : { ...current, [name]: message },
    );
  const submit = () => {
    setAttempted(true);
    if (built.body === null) {
      setFocusTick((tick) => tick + 1);
      return;
    }
    onBuilt(built.body);
  };

  const shown = (name: string) => errors[name] ?? null;
  const { action } = form;
  const adding = ADDING_ACTIONS.has(action);
  const renewing = RENEWING_ACTIONS.has(action);
  const termEnd =
    context.obligations.find((item) => item.key === form.obligationKey)?.endDate ?? null;

  return (
    <FormShell
      formId={formId}
      busy={busy}
      problem={problem}
      unplaced={placed?.unplaced ?? []}
      entries={entries}
      focusTick={focusTick}
      onSubmit={submit}
    >
      <div inert={busy} className="flex w-full max-w-[var(--content-max-form)] flex-col gap-4">
        <dl className="flex flex-col gap-0.5">
          <dt className="text-body-sm font-medium text-fg-1">
            {t("modifications.wizard.change.change")}
          </dt>
          <dd className="text-body text-fg-1">{t(`contracts.workbench.subscription.${action}`)}</dd>
        </dl>
        <Field
          name="obligationKey"
          label={t("modifications.wizard.change.obligation")}
          required
          error={shown("obligationKey")}
          width="text"
        >
          {(control) => (
            <Select<string>
              control={control}
              options={obligationChoices}
              value={form.obligationKey}
              onChange={(value) => set("obligationKey", value)}
              invalid={shown("obligationKey") !== null}
            />
          )}
        </Field>
        {adding ? (
          <TextField
            name="newKey"
            label={t("modifications.wizard.change.newKey")}
            required
            help={t("modifications.wizard.change.newKeyHelp")}
            width="date"
            value={form.newKey}
            onChange={(value) => set("newKey", value)}
            error={shown("newKey")}
          />
        ) : null}
        <div className="flex flex-wrap gap-4">
          <TextField
            name="quantity"
            label={t("modifications.wizard.change.quantity")}
            optional={!adding}
            required={adding}
            help={t(`modifications.wizard.change.quantityHelp.${action}`)}
            width="date"
            inputMode="decimal"
            value={form.quantity}
            onChange={(value) => set("quantity", value)}
            error={shown("quantity")}
          />
          <Field
            name="price"
            label={t("modifications.wizard.change.price")}
            optional
            help={t(`modifications.wizard.change.priceHelp.${action}`)}
            error={shown("price")}
            width="money"
          >
            {(control) => (
              <MoneyInput
                control={control}
                currency={context.currency}
                value={form.price}
                onChange={(text) => set("price", text)}
                onFormatError={(message) => setFormatError("price", message)}
                invalid={shown("price") !== null}
              />
            )}
          </Field>
        </div>
        <div className="flex flex-wrap gap-4">
          <Field
            name="effectiveDate"
            label={t("modifications.wizard.change.effectiveDate")}
            required
            error={shown("effectiveDate")}
            width="date"
          >
            {(control) => (
              <DateInput
                control={control}
                value={form.effectiveDate}
                onChange={(text) => set("effectiveDate", text)}
                onFormatError={(message) => setFormatError("effectiveDate", message)}
                invalid={shown("effectiveDate") !== null}
              />
            )}
          </Field>
          {renewing ? (
            <Field
              name="endDate"
              label={t("modifications.wizard.change.endDate")}
              required
              error={shown("endDate")}
              width="date"
            >
              {(control) => (
                <DateInput
                  control={control}
                  value={form.endDate}
                  onChange={(text) => set("endDate", text)}
                  onFormatError={(message) => setFormatError("endDate", message)}
                  invalid={shown("endDate") !== null}
                />
              )}
            </Field>
          ) : (
            <dl className="flex flex-col gap-0.5">
              <dt className="text-body-sm font-medium text-fg-1">
                {t("modifications.wizard.change.endDate")}
              </dt>
              <dd className="flex h-[var(--control-h)] items-center text-body text-fg-1">
                {termEnd === null
                  ? t("modifications.wizard.change.endsWithObligation")
                  : t("modifications.wizard.change.endsOn", { date: formatDate(termEnd) })}
              </dd>
            </dl>
          )}
        </div>
        <BackdatedNote effectiveDate={form.effectiveDate} latestEvent={latestEvent} />
        <TextField
          name="reference"
          label={t("modifications.wizard.change.reference")}
          required
          help={t("modifications.wizard.change.referenceHelp")}
          value={form.reference}
          onChange={(value) => set("reference", value)}
          error={shown("reference")}
        />
      </div>
    </FormShell>
  );
}

export function ChangeStep({ variant, ...props }: ChangeStepProps) {
  return variant.kind === "general" ? (
    <GeneralForm {...props} initial={variant.initial} />
  ) : (
    <SubscriptionFormView {...props} initial={variant.initial} />
  );
}
