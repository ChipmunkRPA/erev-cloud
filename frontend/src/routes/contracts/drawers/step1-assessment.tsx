// Record assessment and Record criteria met (SCREENS §4.9.1 rev 1.11; supervisor ruling R-89; 04 ACT-01,
// §16.3 COLLECTIBILITY_ASSESSED, T-CON-19; PRD SM-02). The second step of the Step 1 path: once the
// Step 1 review is REVIEWED, one COLLECTIBILITY_ASSESSED per enabled book of the contracting entity cites
// it (`POST /contracts/{id}/events` with `If-Match`). A DRAFT contract's assessment is dated its inception
// date (the assessment in force at inception is the book's latest); behind the not-a-contract gate the
// date is a field that starts at today in the contracting entity's time zone (05 TZ-02). The outcome,
// credit grade and mitigation are the reviewed record's.
//
// The API may refuse the record itself (rev 1.72; REQ-POL-008 on `judgement_record_id`; rulings
// R-102 (c), R-113 (f)): it was reviewed before the draft was last replaced, or it answers No to a
// criterion. The screen cannot know the first before the attempt — the API compares the time the
// booking was written, which no read answers — so it compares nothing: the banner says the API's
// sentence and offers "Record a new Step 1 review", the one way out of a refused record.
import { useId, useMemo, useState } from "react";

import { RefusalBanner } from "../../../components/feedback/RefusalBanner";
import { useNoAnswer, useToast } from "../../../components/feedback/Toast";
import { DateInput } from "../../../components/form/DateInput";
import { Field } from "../../../components/form/Field";
import { Button } from "../../../components/ui/Button";
import { Drawer } from "../../../components/ui/Drawer";
import { useCommandKeys } from "../../../lib/api/commands";
import type { ApiProblem } from "../../../lib/api/problems";
import {
  type Contract,
  CONTRACTS_PATH,
  contractIfMatch,
  type Judgement,
  sendCommand,
} from "../../../lib/api/queries/contracts";
import { judgementStatusLabel } from "../../../lib/api/queries/judgements";
import { placeProblemByEnd } from "../../../lib/api/refusals";
import { formatDate, formatList, formatTimestamp, parseDateInput } from "../../../lib/format";
import { hasMessage, t } from "../../../lib/i18n/t";
import { isProbable } from "../step1";
import { useRefreshRecord } from "./common";

// docs/dev-guide.md DG-FE-06: the body nests one event per book, so the date is placed by the end of
// its pointer (`events.0.effective_date`); what names another member of an event is the banner's.
const ASSESSMENT_FIELDS = { date: ["effective_date"] } as const;
/** The member of an event that names the record it cites (`events.<i>.payload.judgement_record_id`). */
const RECORD_MEMBER = "payload.judgement_record_id";

/**
 * The API refused the record the assessment cites (REQ-POL-008; 04 §16.3 (b)): no other date leads
 * out. Read by the member the error names, as the date's message is placed (DG-FE-06).
 */
function refusesRecord(problem: ApiProblem | null): boolean {
  return problem?.errors.some((error) => error.field?.endsWith(RECORD_MEMBER) === true) ?? false;
}

export interface Step1AssessmentDrawerProps {
  readonly contract: Contract;
  /** The REVIEWED Step 1 record the assessment cites. */
  readonly record: Judgement;
  /** The enabled books of the contracting entity; one assessment each. */
  readonly books: readonly string[];
  /** Today in the contracting entity's time zone, the starting date behind the gate. */
  readonly today: string;
  readonly onClose: () => void;
  /**
   * "Record a new Step 1 review", offered once the API refused the record: this drawer closes and the
   * review drawer opens in its place (DS-CMP-09: one drawer at a time).
   */
  readonly onNewReview: () => void;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value.trim() : null;
}

export function Step1AssessmentDrawer({
  contract,
  record,
  books,
  today,
  onClose,
  onNewReview,
}: Step1AssessmentDrawerProps) {
  const formId = useId();
  const toast = useToast();
  const noAnswer = useNoAnswer();
  const keys = useCommandKeys();
  const refresh = useRefreshRecord();
  // Behind the gate the command records that the criteria are met; a DRAFT contract is assessed.
  const gated = contract.status === "NOT_A_CONTRACT";
  const probable = isProbable(record);
  const [dateText, setDateText] = useState(() => formatDate(today));
  const [date, setDate] = useState<string | null>(today);
  const [attempted, setAttempted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);

  const mode = gated && probable ? "criteriaMet" : "assessment";
  const effective = gated ? date : contract.inception_date;
  const placed = useMemo(() => placeProblemByEnd(problem, ASSESSMENT_FIELDS), [problem]);
  const dateError =
    gated && attempted && effective === null ? t("common.form.date.invalid") : placed.fields.date;
  const questionnaire = record.questionnaire ?? {};
  const grade = text(questionnaire.credit_grade);
  const mitigation = text(questionnaire.mitigation);
  const bookLabel = (code: string) =>
    hasMessage(`shell.context.books.${code}`) ? t(`shell.context.books.${code}`) : code;

  const submit = async () => {
    setAttempted(true);
    if (effective === null) {
      return;
    }
    setSubmitting(true);
    setProblem(null);
    try {
      const appended = await sendCommand(
        keys,
        "POST",
        `${CONTRACTS_PATH}/${contract.id}/events`,
        {
          events: books.map((book) => ({
            event_type: "COLLECTIBILITY_ASSESSED",
            effective_date: effective,
            payload: {
              book,
              is_probable: probable,
              credit_grade: grade,
              mitigation: mitigation === null || mitigation === "NONE" ? null : mitigation,
              judgement_record_id: record.id,
            },
          })),
          evidence_file_ids: [],
        },
        contractIfMatch(contract.head_stream_version),
      );
      if (!appended.ok) {
        setProblem(appended.problem);
        return;
      }
      await refresh();
      toast.show({ tone: "positive", message: t(`contracts.drawer.assessment.saved.${mode}`) });
      onClose();
    } catch {
      // No answer: the next press sends the assessment under the same key (DG-FE-05).
      noAnswer();
    } finally {
      setSubmitting(false);
    }
  };

  const facts: readonly (readonly [string, string])[] = [
    [
      t("contracts.drawer.assessment.review"),
      record.reviewer === null || record.reviewed_at === null
        ? t("contracts.workbench.step1.record", {
            number: record.judgement_no,
            status: judgementStatusLabel(record.status),
          })
        : t("contracts.drawer.assessment.reviewValue", {
            number: record.judgement_no,
            name: record.reviewer.display_name,
            at: formatTimestamp(record.reviewed_at),
          }),
    ],
    [t("contracts.drawer.assessment.conclusion"), record.conclusion],
    [
      t("contracts.drawer.assessment.outcome"),
      t(
        probable
          ? "contracts.drawer.assessment.outcomeProbable"
          : "contracts.drawer.assessment.outcomeNotProbable",
      ),
    ],
    [t("contracts.drawer.assessment.books"), formatList(books.map(bookLabel), "and")],
  ];

  return (
    <Drawer
      open
      title={t(`contracts.drawer.assessment.title.${mode}`)}
      subtitle={contract.external_id}
      initialFocus="field"
      dirty={gated && date !== today}
      submitting={submitting}
      banner={
        <RefusalBanner
          problem={problem}
          placed={placed}
          actions={
            refusesRecord(problem) ? (
              <Button variant="link" onClick={onNewReview}>
                {t("contracts.drawer.assessment.newReview")}
              </Button>
            ) : undefined
          }
        />
      }
      primaryAction={{ label: t(`contracts.drawer.assessment.title.${mode}`), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-03-drawer-step1-assessment"
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <dl className="flex flex-col gap-2 text-body-sm">
          {facts.map(([label, value]) => (
            <div key={label} className="flex flex-col gap-0.5">
              <dt className="text-fg-3">{label}</dt>
              <dd className="text-fg-1">{value}</dd>
            </div>
          ))}
          {gated ? null : (
            <div className="flex flex-col gap-0.5">
              <dt className="text-fg-3">{t("contracts.drawer.assessment.effectiveDate")}</dt>
              <dd className="text-fg-1">
                {t("contracts.drawer.assessment.inceptionDate", {
                  date: formatDate(contract.inception_date),
                })}
              </dd>
            </div>
          )}
        </dl>
        {gated ? (
          <Field
            name="assessment-effective-date"
            label={t("contracts.drawer.assessment.effectiveDate")}
            required
            error={dateError}
            width="date"
          >
            {(control) => (
              <DateInput
                control={control}
                value={dateText}
                onChange={(next) => {
                  setDateText(next);
                  const parsed = parseDateInput(next);
                  setDate(parsed.ok ? parsed.value : null);
                }}
                onValue={setDate}
                invalid={dateError !== null}
              />
            )}
          </Field>
        ) : null}
        {!probable && !gated ? (
          <p className="text-body-sm text-fg-2">{t("contracts.drawer.assessment.gateNote")}</p>
        ) : null}
        {placed.fields.date !== null && !gated ? (
          <p role="alert" className="text-body-sm text-negative-fg">
            {placed.fields.date}
          </p>
        ) : null}
      </form>
    </Drawer>
  );
}
