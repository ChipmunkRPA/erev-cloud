// Record delivery, progress, milestone, cost and return (SCREENS §4.9.3; 04 §16.3 payloads, API-R-30
// `POST /contracts/{id}/events`, `POST /contracts/{id}/events/preview`; BR-REC-01). Each drawer holds the
// fields of its payload, an impact preview below the fields once they validate (a 202 job whose
// `result.summary` is API-S-ImpactSummary) and the primary "Submit for approval": manual events route
// through MANUAL_EVENT approval. "Record return" appends RETURN_RECORDED and, with a credit memo number,
// CREDIT_MEMO_RECORDED in one `events` array; RETURN_EXCEEDS_DELIVERED and REFUND_EXCEEDS_BILLED show
// their messages on the quantity and credit fields. A dry run that ended without a summary is said as
// what it is (SCREENS §4.9.3 rev 1.79): failed or cancelled, with "Retry", or not shown to this reader.
import { useEffect, useId, useMemo, useState } from "react";

import { Banner } from "../../../components/feedback/Banner";
import { RefusalBanner } from "../../../components/feedback/RefusalBanner";
import { useNoAnswer, useToast } from "../../../components/feedback/Toast";
import { DateInput } from "../../../components/form/DateInput";
import { Field } from "../../../components/form/Field";
import { MoneyInput } from "../../../components/form/MoneyInput";
import { Money } from "../../../components/money/Money";
import { Button } from "../../../components/ui/Button";
import { Drawer } from "../../../components/ui/Drawer";
import { useCommandKeys } from "../../../lib/api/commands";
import { isTerminal, type Job, summaryWithheld, useJob } from "../../../lib/api/jobs";
import type { ApiProblem } from "../../../lib/api/problems";
import {
  type Contract,
  contractIfMatch,
  CONTRACTS_PATH,
  sendCommand,
} from "../../../lib/api/queries/contracts";
import type { Obligation } from "../../../lib/api/queries/obligations";
import { placeProblemByEnd } from "../../../lib/api/refusals";
import { formatPercent, formatPeriod } from "../../../lib/format";
import { t } from "../../../lib/i18n/t";
import {
  type Choice,
  decimalText,
  EvidenceField,
  percentToRatio,
  PreviewNotShown,
  RadioGroup,
  requestNumber,
  SelectField,
  TextField,
  uploadEvidence,
  useRefreshRecord,
  yesNoChoices,
} from "./common";

export type EventKind = "delivery" | "progress" | "milestone" | "cost" | "return";
export const EVENT_KINDS: readonly EventKind[] = [
  "delivery",
  "progress",
  "milestone",
  "cost",
  "return",
];

/** SCREENS §5.8: the "Record event" items of an obligation by its recognition method. */
export function eventKindsFor(
  obligation: Pick<Obligation, "recognition_method">,
): readonly EventKind[] {
  switch (obligation.recognition_method) {
    case "UNITS_DELIVERED":
    case "POINT_IN_TIME":
      return ["delivery", "return"];
    case "OUTPUT_PERCENT":
    case "LABOUR_HOURS":
      return ["progress"];
    case "MILESTONE":
      return ["milestone"];
    case "COST_TO_COST":
      return ["cost"];
    default:
      return [];
  }
}

type YesNo = "YES" | "NO";
type Trigger = "DELIVERY" | "ACCEPTANCE" | "SELL_THROUGH" | "BILL_AND_HOLD" | "CONTROL_TRANSFER";
type Measure = "OUTPUT_PERCENT" | "LABOUR_HOURS";
type Purpose = "PROGRESS_INPUT" | "COST_TO_OBTAIN" | "COST_TO_FULFILL";
type Condition = "RESALEABLE" | "NOT_RESALEABLE";

export interface EventForm {
  readonly obligation: string | null;
  readonly quantity: string;
  readonly trigger: Trigger | null;
  readonly effectiveText: string;
  readonly effectiveDate: string | null;
  readonly reference: string;
  readonly comment: string;
  readonly measure: Measure | null;
  readonly progress: string;
  readonly hours: string;
  readonly milestone: string;
  readonly weight: string;
  readonly purpose: Purpose | null;
  readonly amountText: string;
  readonly amount: string | null;
  readonly wasted: YesNo | null;
  readonly uninstalled: YesNo | null;
  readonly payee: string;
  readonly plan: string;
  readonly incremental: YesNo | null;
  readonly clawback: YesNo | null;
  readonly condition: Condition | null;
  readonly creditMemo: string;
  readonly creditText: string;
  readonly credit: string | null;
}

export function emptyEventForm(obligationKey: string | null): EventForm {
  return {
    obligation: obligationKey,
    quantity: "",
    trigger: null,
    effectiveText: "",
    effectiveDate: null,
    reference: "",
    comment: "",
    measure: null,
    progress: "",
    hours: "",
    milestone: "",
    weight: "",
    purpose: null,
    amountText: "",
    amount: null,
    wasted: null,
    uninstalled: null,
    payee: "",
    plan: "",
    incremental: null,
    clawback: null,
    condition: null,
    creditMemo: "",
    creditText: "",
    credit: null,
  };
}

export interface EventItem {
  readonly event_type: string;
  readonly effective_date: string;
  readonly obligation_key: string | null;
  readonly payload: Readonly<Record<string, unknown>>;
}

export interface BuiltEvents {
  readonly events: readonly EventItem[] | null;
  readonly errors: Readonly<Record<string, string>>;
  readonly evidenceRequired: boolean;
}

function flag(value: YesNo | null): boolean | null {
  return value === null ? null : value === "YES";
}

/** The `events` of the drawer's fields, or the field errors that keep it from validating. */
export function buildEvents(kind: EventKind, form: EventForm, currency: string): BuiltEvents {
  const errors: Record<string, string> = {};
  const choose = t("contracts.drawer.choose");
  const date = form.effectiveDate;
  if (date === null) {
    errors.effectiveDate = t("common.form.date.invalid");
  }
  const needsObligation = kind !== "cost";
  if (needsObligation && form.obligation === null) {
    errors.obligation = choose;
  }
  const quantity = decimalText(form.quantity, true);
  let evidenceRequired = kind === "progress" || kind === "milestone" || kind === "cost";
  const items: EventItem[] = [];
  const effective = date ?? "";
  switch (kind) {
    case "delivery":
      if (quantity === null) {
        errors.quantity = t("contracts.drawer.event.quantityError");
      }
      if (form.trigger === null) {
        errors.trigger = choose;
      }
      evidenceRequired = form.trigger === "ACCEPTANCE";
      items.push({
        event_type: "DELIVERY_RECORDED",
        effective_date: effective,
        obligation_key: form.obligation,
        payload: {
          obligation_key: form.obligation,
          quantity,
          trigger: form.trigger,
          source_ref: form.reference.trim() === "" ? null : form.reference.trim(),
        },
      });
      break;
    case "progress": {
      const ratio = percentToRatio(form.progress);
      if (form.measure === null) {
        errors.measure = choose;
      }
      if (ratio === null) {
        errors.progress = t("contracts.drawer.event.percentError");
      }
      const hours = form.hours.trim() === "" ? null : decimalText(form.hours);
      if (form.measure === "LABOUR_HOURS" && hours === null) {
        errors.hours = t("contracts.drawer.event.hoursError");
      }
      items.push({
        event_type: "PROGRESS_RECORDED",
        effective_date: effective,
        obligation_key: form.obligation,
        payload: {
          obligation_key: form.obligation,
          cumulative_progress_ratio: ratio,
          measure: form.measure,
          hours_to_date: form.measure === "LABOUR_HOURS" ? hours : null,
        },
      });
      break;
    }
    case "milestone": {
      const weight = percentToRatio(form.weight);
      if (form.milestone.trim() === "") {
        errors.milestone = t("contracts.drawer.event.milestoneError");
      }
      if (weight === null) {
        errors.weight = t("contracts.drawer.event.percentError");
      }
      items.push({
        event_type: "MILESTONE_ACHIEVED",
        effective_date: effective,
        obligation_key: form.obligation,
        payload: {
          obligation_key: form.obligation,
          milestone_code: form.milestone.trim(),
          cumulative_weight: weight,
        },
      });
      break;
    }
    case "cost":
      if (form.purpose === null) {
        errors.purpose = choose;
      }
      if (form.amount === null) {
        errors.amount = t("common.form.money.invalid");
      }
      items.push({
        event_type: "COST_INCURRED",
        effective_date: effective,
        obligation_key: form.obligation,
        payload: {
          purpose: form.purpose,
          obligation_key: form.obligation,
          amount: { amount: form.amount, currency },
          is_wasted: flag(form.wasted),
          is_uninstalled_material: flag(form.uninstalled),
          payee: form.payee.trim() === "" ? null : form.payee.trim(),
          plan_code: form.plan.trim() === "" ? null : form.plan.trim(),
          is_incremental: flag(form.incremental),
          has_clawback: flag(form.clawback),
        },
      });
      break;
    case "return": {
      if (quantity === null) {
        errors.quantity = t("contracts.drawer.event.quantityError");
      }
      if (form.reference.trim() === "") {
        errors.reference = t("contracts.drawer.event.referenceError");
      }
      if (form.condition === null) {
        errors.condition = choose;
      }
      const memo = form.creditMemo.trim();
      if (memo !== "" && form.credit === null) {
        errors.credit = t("common.form.money.invalid");
      }
      const condition =
        form.condition === null ? "" : t(`contracts.drawer.event.condition.${form.condition}`);
      items.push({
        event_type: "RETURN_RECORDED",
        effective_date: effective,
        obligation_key: form.obligation,
        payload: {
          obligation_key: form.obligation,
          quantity,
          refund_amount: form.credit === null ? null : { amount: form.credit, currency },
          reason: `${form.reference.trim()} · ${condition}`,
        },
      });
      if (memo !== "") {
        items.push({
          event_type: "CREDIT_MEMO_RECORDED",
          effective_date: effective,
          obligation_key: form.obligation,
          payload: {
            credit_memo_number: memo,
            obligation_key: form.obligation,
            amount: { amount: form.credit, currency },
            issue_date: effective,
            reason: form.reference.trim(),
          },
        });
      }
      break;
    }
  }
  return { events: Object.keys(errors).length === 0 ? items : null, errors, evidenceRequired };
}

interface MoneyValue {
  readonly amount: string;
  readonly currency: string;
}

interface ImpactSummary {
  readonly transaction_price_before?: MoneyValue;
  readonly transaction_price_after?: MoneyValue;
  readonly catch_up_total?: MoneyValue;
  readonly revenue_by_period?: readonly {
    readonly period_key: string;
    readonly change: MoneyValue;
    readonly after: MoneyValue;
  }[];
  readonly balances_after?: readonly { readonly balance: string; readonly amount: MoneyValue }[];
  readonly progress_before?: string | null;
  readonly progress_after?: string | null;
}

function summaryOf(result: unknown): ImpactSummary | null {
  if (typeof result !== "object" || result === null || !("summary" in result)) {
    return null;
  }
  const summary = (result as { readonly summary: unknown }).summary;
  return typeof summary === "object" && summary !== null ? (summary as ImpactSummary) : null;
}

/**
 * A dry run that ended without a summary and is not withheld from this reader (SCREENS §4.9.3 rev
 * 1.79; §0.7 SCR-ST-12): the negative banner of a failed job, with the messages of its problem — or
 * the problem's title — and the job's reference. A cancelled job says so and has no problem. "Retry"
 * asks for the preview of the same fields again.
 */
function PreviewEnded({ job, onRetry }: { readonly job: Job; readonly onRetry: () => void }) {
  const messages = job.problem?.errors ?? [];
  return (
    <Banner
      tone="negative"
      title={
        job.state === "CANCELLED"
          ? t("contracts.drawer.preview.cancelled")
          : t("contracts.drawer.preview.failed")
      }
      announce="live"
      headingLevel={4}
      actions={
        <Button variant="link" onClick={onRetry}>
          {t("common.job.retry")}
        </Button>
      }
    >
      {messages.length === 0 ? (
        job.problem === null ? null : (
          <p>{job.problem.title}</p>
        )
      ) : (
        messages.map((error) => <p key={error.message}>{error.message}</p>)
      )}
      <p>{t("common.job.reference", { reference: job.id.slice(0, 8) })}</p>
    </Banner>
  );
}

/**
 * The impact preview panel (SCREENS §4.9 "Preview"): figures of API-S-ImpactSummary, or what became
 * of the dry run in their place (§4.9.3 rev 1.79). A dry run that succeeds stores a summary, whose
 * figures are listed also at 0.00: a finished job without one failed, was cancelled, or holds a
 * summary the API does not answer to this reader.
 */
function PreviewPanel({
  jobId,
  problem,
  onRetry,
}: {
  readonly jobId: string | null;
  readonly problem: ApiProblem | null;
  readonly onRetry: () => void;
}) {
  const job = useJob(jobId);
  const summary = summaryOf(job.data?.result ?? null);
  let body;
  if (problem !== null) {
    // The preview has no field of its own: every sentence of its refusal is the banner's.
    body = <RefusalBanner problem={problem} />;
  } else if (jobId === null) {
    body = <p className="text-body-sm text-fg-3">{t("contracts.drawer.preview.waiting")}</p>;
  } else if (job.data === undefined || !isTerminal(job.data)) {
    body = <p className="text-body-sm text-fg-3">{t("contracts.drawer.preview.running")}</p>;
  } else if (summary === null) {
    body = summaryWithheld(job.data) ? (
      <PreviewNotShown />
    ) : (
      <PreviewEnded job={job.data} onRetry={onRetry} />
    );
  } else {
    body = (
      <dl className="flex flex-col gap-1 text-body-sm">
        {(summary.revenue_by_period ?? []).map((row) => (
          <div key={row.period_key} className="flex justify-between gap-3">
            <dt className="text-fg-2">
              {t("contracts.drawer.preview.revenue", { period: formatPeriod(row.period_key) })}
            </dt>
            <dd>
              <Money
                value={row.change.amount}
                currency={row.change.currency}
                variant="inline"
                delta
              />
            </dd>
          </div>
        ))}
        {summary.catch_up_total === undefined ? null : (
          <div className="flex justify-between gap-3">
            <dt className="text-fg-2">{t("contracts.drawer.preview.catchUp")}</dt>
            <dd>
              <Money
                value={summary.catch_up_total.amount}
                currency={summary.catch_up_total.currency}
                variant="inline"
                delta
              />
            </dd>
          </div>
        )}
        {summary.progress_before === undefined || summary.progress_after === undefined ? null : (
          <div className="flex justify-between gap-3">
            <dt className="text-fg-2">{t("contracts.drawer.preview.progress")}</dt>
            <dd className="num">
              {`${formatPercent(summary.progress_before ?? null)} → ${formatPercent(summary.progress_after ?? null)}`}
            </dd>
          </div>
        )}
        {(summary.balances_after ?? []).map((row) => (
          <div key={row.balance} className="flex justify-between gap-3">
            <dt className="text-fg-2">{balanceLabel(row.balance)}</dt>
            <dd>
              <Money value={row.amount.amount} currency={row.amount.currency} variant="inline" />
            </dd>
          </div>
        ))}
      </dl>
    );
  }
  return (
    <section
      aria-labelledby="record-event-preview"
      className="flex flex-col gap-2 rounded-md border border-hairline p-3"
    >
      <h3 id="record-event-preview" className="text-body-sm font-medium text-fg-1">
        {t("contracts.drawer.preview.title")}
      </h3>
      {body}
    </section>
  );
}

const BALANCE_KEYS: ReadonlySet<string> = new Set([
  "contract_liability",
  "contract_asset",
  "unbilled_receivable",
  "accounts_receivable",
  "refund_liability",
  "return_asset",
  "deposit_liability",
]);

export function balanceLabel(balance: string): string {
  return BALANCE_KEYS.has(balance) ? t(`contracts.balance.${balance}`) : balance;
}

export interface RecordEventDrawerProps {
  readonly contract: Contract;
  readonly obligations: readonly Obligation[];
  readonly kind: EventKind;
  /** The obligation of the pane: preselected and read-only. */
  readonly obligationKey?: string | undefined;
  readonly onClose: () => void;
}

const PREVIEW_DEBOUNCE_MS = 600;

type EventField =
  | "purpose"
  | "obligation"
  | "quantity"
  | "trigger"
  | "measure"
  | "progress"
  | "hours"
  | "milestone"
  | "weight"
  | "amount"
  | "reference"
  | "effectiveDate"
  | "creditMemo"
  | "credit";

/**
 * docs/dev-guide.md DG-FE-06: the fields of the drawer and the endings of the pointers each shows the
 * message of — the body nests one event with its payload (`events.0.payload.quantity`). The drawer
 * shows the fields of one kind of event, and a field that is not on screen takes no pointer: an error
 * on its member is the banner's.
 */
function eventFields(
  kind: EventKind,
  selectsObligation: boolean,
  labourHours: boolean,
): Readonly<Record<EventField, readonly string[]>> {
  const on = (shown: boolean, ...endings: readonly string[]) => (shown ? endings : []);
  return {
    purpose: on(kind === "cost", "purpose"),
    obligation: on(selectsObligation, "obligation_key"),
    quantity: on(kind === "delivery" || kind === "return", "quantity"),
    trigger: on(kind === "delivery", "trigger"),
    measure: on(kind === "progress", "measure"),
    progress: on(kind === "progress", "cumulative_progress_ratio"),
    hours: on(kind === "progress" && labourHours, "hours_to_date"),
    milestone: on(kind === "milestone", "milestone_code"),
    weight: on(kind === "milestone", "cumulative_weight"),
    amount: on(kind === "cost", "amount"),
    reference: on(kind === "delivery" || kind === "return", "source_ref", "reason"),
    effectiveDate: ["effective_date"],
    creditMemo: on(kind === "return", "credit_memo_number"),
    credit: on(kind === "return", "refund_amount"),
  };
}

export function RecordEventDrawer({
  contract,
  obligations,
  kind,
  obligationKey,
  onClose,
}: RecordEventDrawerProps) {
  const formId = useId();
  const toast = useToast();
  const noAnswer = useNoAnswer();
  const keys = useCommandKeys();
  const refresh = useRefreshRecord();
  const [form, setForm] = useState<EventForm>(() => emptyEventForm(obligationKey ?? null));
  const [files, setFiles] = useState<readonly File[]>([]);
  const [attempted, setAttempted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [previewJob, setPreviewJob] = useState<string | null>(null);
  const [previewProblem, setPreviewProblem] = useState<ApiProblem | null>(null);
  // "Retry" on a dry run that did not succeed: the preview of the same fields is asked for again.
  const [previewRound, setPreviewRound] = useState(0);
  const currency = contract.transaction_currency;
  const built = buildEvents(kind, form, currency);
  const serialised = built.events === null ? null : JSON.stringify(built.events);
  const set = <K extends keyof EventForm>(name: K, value: EventForm[K]) =>
    setForm((current) => ({ ...current, [name]: value }));
  const ifMatch = contractIfMatch(contract.head_stream_version);

  useEffect(() => {
    if (serialised === null) {
      setPreviewJob(null);
      return undefined;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      void sendCommand<{ readonly id: string }>(
        keys,
        "POST",
        `${CONTRACTS_PATH}/${contract.id}/events/preview`,
        { events: JSON.parse(serialised) as unknown, comment: null },
        ifMatch,
      ).then(
        (outcome) => {
          if (cancelled) {
            return;
          }
          if (outcome.ok) {
            setPreviewProblem(null);
            setPreviewJob(outcome.data.id);
          } else {
            setPreviewJob(null);
            setPreviewProblem(outcome.problem);
          }
        },
        () => {
          // No answer: no preview is shown; the next change of the form asks again.
          if (!cancelled) {
            setPreviewJob(null);
          }
        },
      );
    }, PREVIEW_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [serialised, contract.id, ifMatch, keys, previewRound]);

  const evidenceMissing = built.evidenceRequired && files.length === 0;
  const shown = (name: string) => (attempted ? (built.errors[name] ?? null) : null);

  const submit = async () => {
    setAttempted(true);
    if (built.events === null || evidenceMissing) {
      return;
    }
    setSubmitting(true);
    setProblem(null);
    try {
      const evidence = await uploadEvidence(keys, files);
      const outcome = await sendCommand<{ readonly approval_request_id?: string | null }>(
        keys,
        "POST",
        `${CONTRACTS_PATH}/${contract.id}/events`,
        {
          events: built.events,
          comment: form.comment.trim() === "" ? null : form.comment.trim(),
          evidence_file_ids: evidence,
        },
        ifMatch,
      );
      if (!outcome.ok) {
        setProblem(outcome.problem);
        return;
      }
      await refresh();
      const requestId = outcome.data?.approval_request_id ?? null;
      toast.show({
        tone: "positive",
        message:
          requestId === null
            ? t("contracts.drawer.event.recorded")
            : t("contracts.drawer.submittedForApproval", {
                request: await requestNumber(requestId),
              }),
      });
      onClose();
    } catch (error) {
      if (error instanceof Error && error.name === "ApiProblem") {
        setProblem(error as ApiProblem);
      } else {
        // No answer: the drawer keeps its input, and the next press sends the same key.
        noAnswer();
      }
    } finally {
      setSubmitting(false);
    }
  };

  const obligationChoices: readonly Choice<string>[] = obligations.map((item) => ({
    value: item.obligation_key,
    label: `${item.obligation_key} · ${item.product.name}`,
  }));
  const readOnlyObligation = obligations.find((item) => item.obligation_key === obligationKey);
  const triggers: readonly Choice<Trigger>[] = (
    ["DELIVERY", "ACCEPTANCE", "SELL_THROUGH", "BILL_AND_HOLD", "CONTROL_TRANSFER"] as const
  ).map((value) => ({ value, label: t(`contracts.drawer.event.trigger.${value}`) }));
  const measures: readonly Choice<Measure>[] = (["OUTPUT_PERCENT", "LABOUR_HOURS"] as const).map(
    (value) => ({ value, label: t(`contracts.drawer.event.measure.${value}`) }),
  );
  const purposes: readonly Choice<Purpose>[] = (
    ["PROGRESS_INPUT", "COST_TO_OBTAIN", "COST_TO_FULFILL"] as const
  ).map((value) => ({ value, label: t(`contracts.drawer.event.purpose.${value}`) }));
  const conditions: readonly Choice<Condition>[] = (["RESALEABLE", "NOT_RESALEABLE"] as const).map(
    (value) => ({ value, label: t(`contracts.drawer.event.condition.${value}`) }),
  );
  const labourHours = form.measure === "LABOUR_HOURS";
  const placed = useMemo(
    () =>
      placeProblemByEnd(problem, eventFields(kind, readOnlyObligation === undefined, labourHours)),
    [problem, kind, readOnlyObligation, labourHours],
  );
  const server = (field: EventField) => placed.fields[field];

  const obligationField =
    readOnlyObligation !== undefined ? (
      <TextField
        name="event-obligation"
        label={t("contracts.drawer.obligation")}
        readOnly
        value={`${readOnlyObligation.obligation_key} · ${readOnlyObligation.product.name}`}
        onChange={() => undefined}
      />
    ) : (
      <SelectField
        name="event-obligation"
        label={t("contracts.drawer.obligation")}
        optional={kind === "cost"}
        options={obligationChoices}
        value={form.obligation}
        onChange={(value) => set("obligation", value)}
        error={shown("obligation") ?? server("obligation")}
      />
    );
  const effectiveField = (
    <Field
      name="event-effective-date"
      label={t("contracts.drawer.event.effectiveDate")}
      required
      error={shown("effectiveDate") ?? server("effectiveDate")}
      width="date"
    >
      {(control) => (
        <DateInput
          control={control}
          value={form.effectiveText}
          onChange={(text) => set("effectiveText", text)}
          onValue={(value) => set("effectiveDate", value)}
          invalid={shown("effectiveDate") !== null}
        />
      )}
    </Field>
  );
  const moneyField = (name: "amount" | "credit", label: string, optional: boolean) => (
    <Field
      name={`event-${name}`}
      label={label}
      optional={optional}
      error={shown(name) ?? server(name)}
      width="money"
    >
      {(control) => (
        <MoneyInput
          control={control}
          currency={currency}
          value={name === "amount" ? form.amountText : form.creditText}
          onChange={(text) => set(name === "amount" ? "amountText" : "creditText", text)}
          onValue={(value) => set(name, value)}
          invalid={shown(name) !== null}
        />
      )}
    </Field>
  );

  return (
    <Drawer
      open
      wide
      title={t(`contracts.drawer.event.title.${kind}`)}
      subtitle={contract.external_id}
      initialFocus="field"
      dirty={JSON.stringify(form) !== JSON.stringify(emptyEventForm(obligationKey ?? null))}
      submitting={submitting}
      banner={<RefusalBanner problem={problem} placed={placed} />}
      primaryAction={{ label: t("contracts.drawer.submitForApproval"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid={`SF-03-drawer-record-${kind}`}
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        {kind === "cost" ? (
          <SelectField
            name="event-purpose"
            label={t("contracts.drawer.event.purpose.label")}
            options={purposes}
            value={form.purpose}
            onChange={(value) => set("purpose", value)}
            error={shown("purpose") ?? server("purpose")}
          />
        ) : null}
        {obligationField}
        {kind === "delivery" || kind === "return" ? (
          <TextField
            name="event-quantity"
            label={t(
              kind === "return"
                ? "contracts.drawer.event.quantityReturned"
                : "contracts.drawer.event.quantity",
            )}
            required
            width="money"
            inputMode="decimal"
            value={form.quantity}
            onChange={(value) => set("quantity", value)}
            error={shown("quantity") ?? server("quantity")}
          />
        ) : null}
        {kind === "delivery" ? (
          <SelectField
            name="event-trigger"
            label={t("contracts.drawer.event.trigger.label")}
            options={triggers}
            value={form.trigger}
            onChange={(value) => set("trigger", value)}
            error={shown("trigger") ?? server("trigger")}
          />
        ) : null}
        {kind === "progress" ? (
          <>
            <SelectField
              name="event-measure"
              label={t("contracts.drawer.event.measure.label")}
              options={measures}
              value={form.measure}
              onChange={(value) => set("measure", value)}
              error={shown("measure") ?? server("measure")}
            />
            <TextField
              name="event-progress"
              label={t("contracts.drawer.event.progress")}
              required
              width="money"
              inputMode="decimal"
              value={form.progress}
              onChange={(value) => set("progress", value)}
              error={shown("progress") ?? server("progress")}
            />
            {labourHours ? (
              <TextField
                name="event-hours"
                label={t("contracts.drawer.event.hours")}
                required
                width="money"
                inputMode="decimal"
                value={form.hours}
                onChange={(value) => set("hours", value)}
                error={shown("hours") ?? server("hours")}
              />
            ) : null}
          </>
        ) : null}
        {kind === "milestone" ? (
          <>
            <TextField
              name="event-milestone"
              label={t("contracts.drawer.event.milestone")}
              required
              value={form.milestone}
              onChange={(value) => set("milestone", value)}
              error={shown("milestone") ?? server("milestone")}
            />
            <TextField
              name="event-weight"
              label={t("contracts.drawer.event.weight")}
              required
              width="money"
              inputMode="decimal"
              value={form.weight}
              onChange={(value) => set("weight", value)}
              error={shown("weight") ?? server("weight")}
            />
          </>
        ) : null}
        {kind === "cost" ? (
          <>
            {moneyField("amount", t("contracts.drawer.event.amount"), false)}
            {(
              [
                ["wasted", "contracts.drawer.event.wasted"],
                ["uninstalled", "contracts.drawer.event.uninstalled"],
                ["incremental", "contracts.drawer.event.incremental"],
                ["clawback", "contracts.drawer.event.clawback"],
              ] as const
            ).map(([name, key]) => (
              <RadioGroup
                key={name}
                legend={t(key)}
                options={yesNoChoices()}
                value={form[name]}
                onChange={(value) => set(name, value)}
              />
            ))}
            <TextField
              name="event-payee"
              label={t("contracts.drawer.event.payee")}
              optional
              value={form.payee}
              onChange={(value) => set("payee", value)}
            />
            <TextField
              name="event-plan"
              label={t("contracts.drawer.event.planCode")}
              optional
              value={form.plan}
              onChange={(value) => set("plan", value)}
            />
          </>
        ) : null}
        {kind === "delivery" || kind === "return" ? (
          <TextField
            name="event-reference"
            label={t(
              kind === "return"
                ? "contracts.drawer.event.returnReference"
                : "contracts.drawer.event.reference",
            )}
            optional={kind === "delivery"}
            required={kind === "return"}
            value={form.reference}
            onChange={(value) => set("reference", value)}
            error={shown("reference") ?? server("reference")}
          />
        ) : null}
        {effectiveField}
        {kind === "return" ? (
          <>
            <SelectField
              name="event-condition"
              label={t("contracts.drawer.event.condition.label")}
              options={conditions}
              value={form.condition}
              onChange={(value) => set("condition", value)}
              error={shown("condition")}
            />
            <TextField
              name="event-credit-memo"
              label={t("contracts.drawer.event.creditMemo")}
              optional
              value={form.creditMemo}
              onChange={(value) => set("creditMemo", value)}
              error={server("creditMemo")}
            />
            {moneyField("credit", t("contracts.drawer.event.creditAmount"), true)}
          </>
        ) : null}
        <EvidenceField
          name="event-evidence"
          label={t("contracts.drawer.evidence")}
          required={built.evidenceRequired}
          files={files}
          onChange={setFiles}
          error={attempted && evidenceMissing ? t("contracts.drawer.event.evidenceError") : null}
        />
        {kind === "delivery" || kind === "progress" ? (
          <TextField
            name="event-comment"
            label={t("contracts.drawer.comment")}
            optional
            multiline
            value={form.comment}
            onChange={(value) => set("comment", value)}
          />
        ) : null}
        <PreviewPanel
          jobId={previewJob}
          problem={previewProblem}
          onRetry={() => setPreviewRound((round) => round + 1)}
        />
      </form>
    </Drawer>
  );
}
