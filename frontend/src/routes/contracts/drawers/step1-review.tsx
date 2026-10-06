// Record Step 1 review (SCREENS §4.9.1 rev 1.11; supervisor ruling R-89; 04 T-CON-19, §16.10). The five
// ASC 606-10-25-1 criteria with notes, credit grade, mitigation, termination, rationale and evidence.
// Commands: `POST /judgements` (subject the contract; topic NOT_A_CONTRACT when collectibility is not
// probable, else COLLECTIBILITY; the criteria, notes and termination are the questionnaire's evidence
// members, and a NOT_A_CONTRACT record names the two members the engine reads behind the gate,
// `consideration_nonrefundable` and `event_c_met_on`, ENGINE_SPEC S02-R-07), then
// `POST /judgements/{id}/submit` for review. No event is appended here: the review
// request hashes the contract's head, so the assessment is recorded by the second step of the Step 1
// path (`./step1-assessment`) once the record is reviewed.
import { useId, useMemo, useState } from "react";

import { RefusalBanner } from "../../../components/feedback/RefusalBanner";
import { useNoAnswer, useToast } from "../../../components/feedback/Toast";
import { DateInput } from "../../../components/form/DateInput";
import { Field } from "../../../components/form/Field";
import { ReasonField, reasonError } from "../../../components/form/ReasonField";
import { Drawer } from "../../../components/ui/Drawer";
import { useCommandKeys } from "../../../lib/api/commands";
import type { ApiProblem } from "../../../lib/api/problems";
import {
  type Contract,
  JUDGEMENTS_PATH,
  type Judgement,
  sendCommand,
  sendStep,
} from "../../../lib/api/queries/contracts";
import { placeProblemByEnd } from "../../../lib/api/refusals";
import { parseDateInput } from "../../../lib/format";
import { t } from "../../../lib/i18n/t";
import {
  type Choice,
  EvidenceField,
  RadioGroup,
  SelectField,
  TextField,
  uploadEvidence,
  useRefreshRecord,
  yesNoChoices,
} from "./common";

export const CRITERIA = ["a", "b", "c", "d", "e"] as const;
export type Criterion = (typeof CRITERIA)[number];
type YesNo = "YES" | "NO";
type Mitigation = "NONE" | "ADVANCE_PAYMENT" | "STOP_SERVICE";
type Party = "NONE" | "CUSTOMER" | "ENTITY" | "BOTH";

// docs/dev-guide.md DG-FE-06: the record's body nests the questionnaire, so a message is placed by the
// end of its pointer. The criteria, their notes, the mitigation and the termination show no message of
// the API: an error on those members is the banner's.
const REVIEW_FIELDS = {
  nonrefundable: ["questionnaire.consideration_nonrefundable"],
  stopped: ["questionnaire.event_c_met_on"],
  grade: ["credit_grade"],
  rationale: ["rationale"],
} as const;
// The two questions of a not-probable outcome are on screen only while collectibility is not probable.
const REVIEW_FIELDS_OF_PROBABLE = { ...REVIEW_FIELDS, nonrefundable: [], stopped: [] } as const;

export interface Step1ReviewDrawerProps {
  readonly contract: Contract;
  readonly onClose: () => void;
}

export function Step1ReviewDrawer({ contract, onClose }: Step1ReviewDrawerProps) {
  const formId = useId();
  const toast = useToast();
  const noAnswer = useNoAnswer();
  // One press creates the record and submits it: the keys of both steps (DG-FE-05 rev 1.156).
  const keys = useCommandKeys();
  const refresh = useRefreshRecord();
  const [criteria, setCriteria] = useState<Readonly<Record<Criterion, YesNo | null>>>({
    a: null,
    b: null,
    c: null,
    d: contract.has_commercial_substance ? "YES" : null,
    e: null,
  });
  const [notes, setNotes] = useState<Readonly<Record<Criterion, string>>>({
    a: "",
    b: "",
    c: "",
    d: "",
    e: "",
  });
  const [grade, setGrade] = useState("");
  const [mitigation, setMitigation] = useState<Mitigation>("NONE");
  const [party, setParty] = useState<Party>("NONE");
  const [penalty, setPenalty] = useState<YesNo | null>(null);
  const [notice, setNotice] = useState("");
  // The NOT_A_CONTRACT questionnaire (04 T-CON-19), asked only while collectibility is not probable.
  const [nonrefundable, setNonrefundable] = useState<YesNo | null>(null);
  const [stoppedText, setStoppedText] = useState("");
  const [rationale, setRationale] = useState("");
  const [files, setFiles] = useState<readonly File[]>([]);
  const [attempted, setAttempted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);

  const mitigations: readonly Choice<Mitigation>[] = [
    { value: "NONE", label: t("contracts.drawer.step1.mitigation.none") },
    { value: "ADVANCE_PAYMENT", label: t("contracts.drawer.step1.mitigation.advancePayment") },
    { value: "STOP_SERVICE", label: t("contracts.drawer.step1.mitigation.stopService") },
  ];
  const parties: readonly Choice<Party>[] = [
    { value: "NONE", label: t("contracts.drawer.step1.party.none") },
    { value: "CUSTOMER", label: t("contracts.drawer.step1.party.customer") },
    { value: "ENTITY", label: t("contracts.drawer.step1.party.entity") },
    { value: "BOTH", label: t("contracts.drawer.step1.party.both") },
  ];
  const noticeInvalid = notice.trim() !== "" && !/^\d+$/.test(notice.trim());
  const notProbable = criteria.e === "NO";
  const placed = useMemo(
    () =>
      placeProblemByEnd<keyof typeof REVIEW_FIELDS>(
        problem,
        notProbable ? REVIEW_FIELDS : REVIEW_FIELDS_OF_PROBABLE,
      ),
    [problem, notProbable],
  );
  const stopped = parseDateInput(stoppedText);
  const stoppedInvalid = notProbable && stoppedText.trim() !== "" && !stopped.ok;
  const missing =
    CRITERIA.some((criterion) => criteria[criterion] === null) ||
    (notProbable && nonrefundable === null);

  const submit = async () => {
    setAttempted(true);
    if (missing || noticeInvalid || stoppedInvalid || reasonError(rationale) !== null) {
      return;
    }
    setSubmitting(true);
    setProblem(null);
    try {
      const evidence = await uploadEvidence(keys, files);
      const probable = criteria.e === "YES";
      // Kept until the record is submitted: a second press after a lost or refused submission replays
      // the record this press created instead of creating another.
      const created = await sendStep<Judgement>(keys, "POST", JUDGEMENTS_PATH, {
        // 04 §16.3 (b): a not-probable assessment cites a record of topic NOT_A_CONTRACT.
        topic: probable ? "COLLECTIBILITY" : "NOT_A_CONTRACT",
        subject_type: "contract",
        subject_id: contract.id,
        conclusion: t(
          probable
            ? "contracts.drawer.step1.conclusion.probable"
            : "contracts.drawer.step1.conclusion.notProbable",
        ),
        rationale: rationale.trim(),
        codification_refs: ["606-10-25-1"],
        questionnaire: {
          criteria,
          notes,
          credit_grade: grade.trim() === "" ? null : grade.trim(),
          mitigation,
          termination: {
            party,
            has_penalty: penalty === null ? null : penalty === "YES",
            notice_days: notice.trim() === "" ? null : Number(notice.trim()),
          },
          evidence_file_ids: evidence,
          ...(probable
            ? {}
            : {
                consideration_nonrefundable: nonrefundable === "YES",
                event_c_met_on: stopped.ok ? stopped.value : null,
              }),
        },
      });
      if (!created.ok) {
        setProblem(created.problem);
        return;
      }
      const submitted = await sendCommand(
        keys,
        "POST",
        `${JUDGEMENTS_PATH}/${created.data.id}/submit`,
        { comment: null },
      );
      if (!submitted.ok) {
        setProblem(submitted.problem);
        return;
      }
      keys.clear();
      await refresh();
      toast.show({
        tone: "positive",
        message: t("contracts.drawer.step1.saved", { number: created.data.judgement_no }),
      });
      onClose();
    } catch (error) {
      if (error instanceof Error && error.name === "ApiProblem") {
        setProblem(error as ApiProblem);
      } else {
        // No answer: the drawer keeps its input, and the next press sends the same keys.
        noAnswer();
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Drawer
      open
      wide
      title={t("contracts.drawer.step1.title")}
      subtitle={contract.external_id}
      initialFocus="field"
      dirty={rationale !== "" || CRITERIA.some((criterion) => criteria[criterion] !== null)}
      submitting={submitting}
      banner={<RefusalBanner problem={problem} placed={placed} />}
      primaryAction={{ label: t("contracts.drawer.step1.save"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-03-drawer-step1-review"
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        {CRITERIA.map((criterion) => (
          <div key={criterion} className="flex flex-col gap-2">
            <RadioGroup
              legend={t(`contracts.drawer.step1.criterion.${criterion}`)}
              options={yesNoChoices()}
              value={criteria[criterion]}
              onChange={(value) => setCriteria((current) => ({ ...current, [criterion]: value }))}
              error={
                attempted && criteria[criterion] === null
                  ? t("contracts.drawer.step1.criterionRequired")
                  : null
              }
            />
            <TextField
              name={`step1-note-${criterion}`}
              label={t("contracts.drawer.step1.note")}
              optional
              value={notes[criterion]}
              onChange={(value) => setNotes((current) => ({ ...current, [criterion]: value }))}
            />
          </div>
        ))}
        {notProbable ? (
          <>
            <RadioGroup
              legend={t("contracts.drawer.step1.nonrefundable")}
              options={yesNoChoices()}
              value={nonrefundable}
              onChange={setNonrefundable}
              error={
                attempted && nonrefundable === null
                  ? t("contracts.drawer.step1.criterionRequired")
                  : placed.fields.nonrefundable
              }
            />
            <Field
              name="step1-transfer-stopped"
              label={t("contracts.drawer.step1.transferStopped")}
              optional
              help={t("contracts.drawer.step1.transferStoppedHelp")}
              error={stoppedInvalid ? t("common.form.date.invalid") : placed.fields.stopped}
              width="date"
            >
              {(control) => (
                <DateInput
                  control={control}
                  value={stoppedText}
                  onChange={setStoppedText}
                  invalid={stoppedInvalid || placed.fields.stopped !== null}
                />
              )}
            </Field>
          </>
        ) : null}
        <TextField
          name="step1-credit-grade"
          label={t("contracts.drawer.step1.creditGrade")}
          optional
          value={grade}
          onChange={setGrade}
          error={placed.fields.grade}
        />
        <SelectField
          name="step1-mitigation"
          label={t("contracts.drawer.step1.mitigation.label")}
          options={mitigations}
          value={mitigation}
          onChange={setMitigation}
        />
        <SelectField
          name="step1-termination"
          label={t("contracts.drawer.step1.party.label")}
          options={parties}
          value={party}
          onChange={setParty}
        />
        <RadioGroup
          legend={t("contracts.drawer.step1.penalty")}
          options={yesNoChoices()}
          value={penalty}
          onChange={setPenalty}
        />
        <TextField
          name="step1-notice-days"
          label={t("contracts.drawer.step1.noticeDays")}
          optional
          inputMode="numeric"
          width="money"
          value={notice}
          onChange={setNotice}
          error={noticeInvalid ? t("contracts.drawer.wholeNumber") : null}
        />
        <ReasonField
          name="step1-rationale"
          label={t("contracts.drawer.rationale")}
          value={rationale}
          onChange={setRationale}
          showError={attempted}
          error={placed.fields.rationale}
        />
        <EvidenceField
          name="step1-evidence"
          label={t("contracts.drawer.evidence")}
          files={files}
          onChange={setFiles}
        />
      </form>
    </Drawer>
  );
}
