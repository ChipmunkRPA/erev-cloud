// The version drawer of an estimated element (SCREENS §8.4, §8.10; DESIGN_SYSTEM DS-CMP-09, DS-CMP-10
// inline editing, DS-CMP-21, DS-CMP-24; 04 API-R-32 `POST /estimates/{id}/versions`,
// `PATCH /estimate-versions/{id}`, `POST /estimate-versions/{id}/preview`, `/submit`, API-R-12
// attachments, T-CON-19 `CONSTRAINT`; PRD SM-04, POL-040, POL-183; BUILD_SPEC CTR-25).
//
// "New estimate version · <element code>": the effective date, the kind's own fields, the rationale and
// the evidence, with the preview of the saved draft below them. "Save draft" stores the version (POST
// the first time, PATCH afterwards), attaches the files, records the constraint judgement where one
// was written and then runs the preview; "Submit for approval" does the same and submits. The drawer
// keeps what a step created, so a step that failed is taken up again and nothing is created twice;
// a step whose answer was lost goes out again under the key it had (DG-FE-05 rev 1.156).
// The method and the element type are the element's and are shown, never edited (04 T-CON-12).
//
// The constraint's judgement record (SCREENS §8.4 as bound, rev 1.64; 04 §16.14 rev 1.241; PRD IMP-140):
// a variable-consideration version is submitted with a `CONSTRAINT` record that is sent for review or
// reviewed. A new version names none — the record of the version it starts from is that version's —
// and a record that does not stand is replaced: the conclusion field stands until the version names a
// record that does, and "Submit for approval" asks for it. "Save draft" stores the version without it.
//
// The classification of an estimate of total costs is asked and not stored: 04 holds no member for it,
// and its one purpose is to keep an error correction out of this path (POL-183).
//
// A preview this reader is not shown (SCREENS §8.4 rev 1.79; 04 API-S-Job `result` rev 1.314): the job
// of the dry run answers its summary to a reader who holds `contract.read` for every entity of the
// contract's combination group. To every other reader the panel shows the notice of the event drawers
// in the place of the table, and does not offer "Run preview"; the next save runs it as before.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { Banner } from "../../components/feedback/Banner";
import { JobProgress } from "../../components/feedback/JobProgress";
import { useToast } from "../../components/feedback/Toast";
import { DateInput } from "../../components/form/DateInput";
import { ErrorSummary, type FormErrorEntry } from "../../components/form/ErrorSummary";
import { Field, fieldId } from "../../components/form/Field";
import { MoneyInput } from "../../components/form/MoneyInput";
import { type LineColumn, LineEditor } from "../../components/line-editor/LineEditor";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { useCommand, useCommandKeys } from "../../lib/api/commands";
import { summaryWithheld } from "../../lib/api/jobs";
import { ApiProblem } from "../../lib/api/problems";
import {
  ATTACHMENTS_PATH,
  type Contract,
  type Judgement,
  JUDGEMENTS_PATH,
  sendCommand,
} from "../../lib/api/queries/contracts";
import {
  type Estimate,
  ESTIMATE_CONSTRAINT_RECORD,
  ESTIMATE_EVIDENCE_REQUIRED,
  ESTIMATE_RECORD_KEYS,
  ESTIMATE_VERSION_SUBJECT,
  type EstimateImpact,
  type EstimatePreviewJob,
  type EstimateVersion,
  estimateVersionPath,
  estimateVersionsPath,
  fetchJudgement,
  fetchVersionAttachments,
  judgementKey,
  versionAttachmentsKey,
} from "../../lib/api/queries/estimates";
import { judgementStatusLabel, recordStands } from "../../lib/api/queries/judgements";
import type { components } from "../../lib/api/schema";
import {
  buildVersion,
  CONSTRAINT_FACTORS,
  countText,
  type EacClassification,
  emptyScenario,
  EVIDENCE_REQUIRED,
  factorFlag,
  KIND_MEMBERS,
  type Member,
  MEMO_MAX_LENGTH,
  methodLocked,
  type ScenarioRow,
  type VersionForm,
  versionForm,
} from "../../lib/forms/estimate";
import { formatNumber } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import {
  EvidenceField,
  PreviewNotShown,
  RadioGroup,
  ReadOnlyItem,
  TextField,
  uploadEvidence,
} from "./drawers/common";
import {
  elementTypeLabel,
  EstimatePreview,
  type Failure,
  FailureNotice,
  MethodChip,
  type PeriodLabel,
} from "./estimate-parts";

type JudgementCreateBody = components["schemas"]["JudgementCreateIn"];

/** A new version that starts from the figures of `source`, or the edit of a version that can be edited. */
export type VersionDrawerMode =
  | { readonly kind: "new"; readonly source: EstimateVersion | null }
  | { readonly kind: "edit"; readonly version: EstimateVersion };

export interface VersionDrawerProps {
  readonly contract: Contract;
  readonly estimate: Estimate;
  readonly mode: VersionDrawerMode;
  /** The viewer may record judgement records (`judgement.create`). */
  readonly canJudge: boolean;
  readonly contextPeriod: string | null;
  readonly periodLabel: PeriodLabel;
  /**
   * The DRAFT modification a new version is created inside (SCREENS §7.4 "Add estimate version"; 04
   * T-CON-13 `modification_id`, §16.14 rev 1.210): the `POST` names it, and no later command changes
   * it. The modification's row lists the version and is among the reads every estimate command
   * refreshes (`ESTIMATE_RECORD_KEYS`).
   */
  readonly modificationId?: string | undefined;
  readonly onClose: () => void;
  /** The version was submitted: the drawer has done its work. */
  readonly onSubmitted: (version: EstimateVersion) => void;
}

const SCENARIO_COLUMNS = ["outcome", "amount", "probability"] as const;
type ScenarioColumn = (typeof SCENARIO_COLUMNS)[number];
const EVIDENCE_FIELD = "evidence";
const CONCLUSION_FIELD = "constraintConclusion";

function isImpact(value: unknown): value is EstimateImpact {
  return (
    typeof value === "object" &&
    value !== null &&
    "transaction_price_before" in value &&
    "catch_up_total" in value &&
    "revenue_by_period" in value
  );
}

/** The index of a scenario cell's row in the field name the API uses (`scenarios.<index>.<column>`). */
function scenarioField(rows: readonly ScenarioRow[], rowId: string, column: string): string {
  return `scenarios.${String(rows.findIndex((row) => row.id === rowId))}.${column}`;
}

export function VersionDrawer({
  contract,
  estimate,
  mode,
  canJudge,
  contextPeriod,
  periodLabel,
  modificationId,
  onClose,
  onSubmitted,
}: VersionDrawerProps) {
  const queryClient = useQueryClient();
  const toast = useToast();
  // The keys of the steps a press sends beside the two hook commands (DG-FE-05 rev 1.156).
  const keys = useCommandKeys();
  const formId = useId();
  const previewId = useId();
  const attachedId = useId();
  const kind = estimate.estimate_kind;
  const method = estimate.method;
  const source = mode.kind === "edit" ? mode.version : mode.source;
  const currency = source?.currency ?? contract.transaction_currency;
  const variable = kind === "VARIABLE_CONSIDERATION";

  const scenarioIds = useRef(0);
  const nextScenarioId = () => {
    scenarioIds.current += 1;
    return `scenario-${String(scenarioIds.current)}`;
  };
  // The form of the version the drawer opened with; it does not follow a later read of that version.
  const [clean, setClean] = useState<VersionForm>(() =>
    versionForm(kind, source, currency, mode.kind, () => nextScenarioId()),
  );
  const [form, setForm] = useState(clean);
  const [versionId, setVersionId] = useState<string | null>(
    mode.kind === "edit" ? mode.version.id : null,
  );
  const [saved, setSaved] = useState<EstimateVersion | null>(null);
  const [files, setFiles] = useState<readonly File[]>([]);
  // The native file input keeps its own list: it is mounted again once its files are attached.
  const [evidenceRound, setEvidenceRound] = useState(0);
  const [conclusion, setConclusion] = useState("");
  // The record the VERSION names: a new version names none, whatever the version it starts from
  // names — its `POST` sends no record and the API copies none (04 §16.14 rev 1.241).
  const [recordId, setRecordId] = useState<string | null>(
    mode.kind === "edit" ? mode.version.judgement_record_id : null,
  );
  // The record this drawer created and sent for review, as its submission answered it.
  const [made, setMade] = useState<Judgement | null>(null);
  const [draftRecord, setDraftRecord] = useState<Judgement | null>(null);
  const [attempted, setAttempted] = useState<"save" | "submit" | null>(null);
  const [focusTick, setFocusTick] = useState(0);
  const [formatErrors, setFormatErrors] = useState<Readonly<Record<string, string>>>({});
  const [failure, setFailure] = useState<Failure | null>(null);
  const [busy, setBusy] = useState<"save" | "submit" | null>(null);

  const carried = mode.kind === "edit" ? mode.version.parameters : (mode.source?.parameters ?? {});
  const built = useMemo(
    () => buildVersion(kind, method, form, currency, carried),
    // The parameters carried over are those of the version the drawer opened with.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [kind, method, form, currency],
  );
  const members = KIND_MEMBERS[kind];

  const attachments = useQuery({
    queryKey: versionAttachmentsKey(versionId ?? ""),
    queryFn: () => fetchVersionAttachments(versionId ?? ""),
    enabled: versionId !== null,
  });
  // The record the version names, read by its id: its subject may be the version, its modification,
  // the contract or an obligation (04 §16.14 rev 1.241).
  const ownRecord = made !== null && made.id === recordId;
  const named = useQuery({
    queryKey: judgementKey(recordId ?? ""),
    queryFn: () => fetchJudgement(recordId ?? ""),
    enabled: variable && recordId !== null && !ownRecord,
    retry: false,
  });
  const record = ownRecord ? made : (named.data ?? null);
  // A record that is neither sent for review nor reviewed — rejected, a draft, superseded, discarded
  // — is not the one the submission asks for: a new conclusion replaces it.
  const replaced = record !== null && !recordStands(record.status);
  // The version needs a conclusion: it names no record, or one that does not stand. While the read
  // of a named record has not answered, or failed, the API alone says whether it stands.
  const asksConclusion = variable && (recordId === null || replaced);
  const conclusionShown = asksConclusion && canJudge;
  const conclusionOwed = conclusionShown && conclusion.trim() === "";

  const create = useCommand<EstimateVersion>({
    method: "POST",
    path: estimateVersionsPath(estimate.id),
  });
  const preview = useCommand<EstimatePreviewJob>({
    method: "POST",
    path: `${estimateVersionPath(versionId ?? estimate.id)}/preview`,
  });
  const job = preview.job;

  // The preview is of the stored draft: it runs after every save of this drawer.
  const stamp = saved === null ? null : `${saved.id}:${saved.updated_at}`;
  const previewed = useRef<string | null>(null);
  const [previewUnreached, setPreviewUnreached] = useState(false);
  const runPreview = async () => {
    setPreviewUnreached(false);
    const outcome = await preview.submit({});
    setPreviewUnreached(outcome.kind === "network-error");
  };
  useEffect(() => {
    if (stamp !== null && previewed.current !== stamp) {
      previewed.current = stamp;
      void runPreview();
    }
    // `runPreview` sends the command of this render; the effect follows the saved version.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stamp]);

  const evidenceCount = (attachments.data?.length ?? 0) + files.length;
  const evidenceNeeded = EVIDENCE_REQUIRED.has(kind);
  const evidenceError =
    attempted === "submit" && evidenceNeeded && evidenceCount === 0
      ? t("contracts.drawer.event.evidenceError")
      : null;
  const conclusionError =
    attempted !== null && conclusion.trim().length > MEMO_MAX_LENGTH
      ? t("contracts.estimates.error.tooLong", { max: countText(MEMO_MAX_LENGTH) })
      : attempted === "submit" && conclusionOwed
        ? t("contracts.estimates.judgement.required")
        : null;
  const errorCorrection = kind === "EAC" && form.classification === "ERROR_CORRECTION";

  // The fields in the order of the form: the error summary lists them so.
  const shownFields = [
    "effective_date",
    "scenarios",
    ...form.scenarios.flatMap((_, index) =>
      SCENARIO_COLUMNS.map((column) => `scenarios.${String(index)}.${column}`),
    ),
    ...members.map((member) => member.id),
    "rationale",
  ];
  // Two findings of a submission stand on a field of this form although the API names none of its
  // fields (PRD IMP-138: no field; IMP-140: `judgement_record_id`): they are placed by their rule.
  const placedRules = [
    ESTIMATE_EVIDENCE_REQUIRED,
    ...(conclusionShown ? [ESTIMATE_CONSTRAINT_RECORD] : []),
  ];
  const serverFields: Record<string, string> = {};
  const placed: Record<string, string> = {};
  if (failure !== null && failure !== "unreached") {
    for (const error of failure.errors) {
      if (error.rule_id === ESTIMATE_EVIDENCE_REQUIRED) {
        placed[EVIDENCE_FIELD] ??= error.message;
      } else if (error.rule_id === ESTIMATE_CONSTRAINT_RECORD && conclusionShown) {
        placed[CONCLUSION_FIELD] ??= error.message;
      } else if (error.field !== null && shownFields.includes(error.field)) {
        serverFields[error.field] ??= error.message;
      }
    }
  }
  const errors: Readonly<Record<string, string>> = {
    ...formatErrors,
    ...serverFields,
    ...(attempted === null ? {} : built.errors),
    ...(evidenceError === null ? {} : { [EVIDENCE_FIELD]: evidenceError }),
    ...(conclusionError === null ? {} : { [CONCLUSION_FIELD]: conclusionError }),
    // While the API's refusal stands its sentence is the one the field shows.
    ...placed,
  };
  const shown = (name: string) => errors[name] ?? null;
  const entries: FormErrorEntry[] = [...shownFields, CONCLUSION_FIELD, EVIDENCE_FIELD].flatMap(
    (name) => (name in errors ? [{ name, message: errors[name] ?? "" }] : []),
  );

  const change = (next: VersionForm) => {
    setForm(next);
    if (failure !== null) {
      setFailure(null);
    }
  };
  const setValue = (id: string, value: string) =>
    change({ ...form, values: { ...form.values, [id]: value } });
  const setFlag = (id: string, value: boolean) =>
    change({ ...form, flags: { ...form.flags, [id]: value } });
  const setFormatError = (name: string, message: string | null) =>
    setFormatErrors((current) => {
      const rest = Object.fromEntries(Object.entries(current).filter(([key]) => key !== name));
      return message === null ? rest : { ...rest, [name]: message };
    });

  const refresh = () =>
    Promise.all(
      ESTIMATE_RECORD_KEYS.map((queryKey) => queryClient.invalidateQueries({ queryKey })),
    );

  /** One step of the sequence: its answer, or null after the failure was shown. */
  const step = async <T,>(
    send: "POST" | "PATCH",
    path: string,
    body: unknown,
  ): Promise<{ readonly data: T } | null> => {
    const result = await sendCommand<T>(keys, send, path, body);
    if (!result.ok) {
      setFailure(result.problem);
      return null;
    }
    return { data: result.data };
  };

  /** Stores the version, its evidence and its constraint judgement; null when a step failed. */
  const persist = async (): Promise<EstimateVersion | null> => {
    if (built.body === null) {
      return null;
    }
    let row: EstimateVersion;
    if (versionId === null) {
      const outcome = await create.submit(
        modificationId === undefined
          ? built.body
          : { ...built.body, modification_id: modificationId },
      );
      if (outcome.kind !== "succeeded" || outcome.data === null) {
        setFailure(outcome.kind === "failed" ? outcome.problem : "unreached");
        return null;
      }
      row = outcome.data;
      setVersionId(row.id);
    } else {
      const updated = await step<EstimateVersion>(
        "PATCH",
        estimateVersionPath(versionId),
        built.body,
      );
      if (updated === null) {
        return null;
      }
      row = updated.data;
    }
    setClean(form);
    for (const file of files) {
      const [fileId] = await uploadEvidence(keys, [file]);
      const attached = await step("POST", ATTACHMENTS_PATH, {
        subject_type: ESTIMATE_VERSION_SUBJECT,
        subject_id: row.id,
        file_object_id: fileId,
        description: null,
      });
      if (attached === null) {
        return null;
      }
      setFiles((current) => current.filter((item) => item !== file));
    }
    // A conclusion was written for a version that names no standing record: it becomes a record of
    // its own, is sent for review and is linked — in the place of one that did not stand, which stays
    // as it is (only its creator may revise it, 04 T-CON-19).
    if (conclusionShown && conclusion.trim() !== "") {
      let record = draftRecord;
      if (record === null) {
        const created = await step<Judgement>("POST", JUDGEMENTS_PATH, {
          topic: "CONSTRAINT",
          subject_type: ESTIMATE_VERSION_SUBJECT,
          subject_id: row.id,
          // The route defaults no contract for an estimate version, and a record without one is
          // read by no computation of the contract (04 T-CON-19).
          contract_id: contract.id,
          conclusion: conclusion.trim(),
          rationale: row.rationale,
          // 04 T-CON-19: `remote` attests the remoteness of a breakage (ENGINE_SPEC_B S09-R-29).
          questionnaire: { estimate_key: estimate.element_code, remote: false },
        } satisfies JudgementCreateBody);
        if (created === null) {
          return null;
        }
        record = created.data;
        setDraftRecord(record);
      }
      const submitted = await step<Judgement>("POST", `${JUDGEMENTS_PATH}/${record.id}/submit`, {
        comment: null,
      });
      if (submitted === null) {
        return null;
      }
      const linkedRow = await step<EstimateVersion>("PATCH", estimateVersionPath(row.id), {
        judgement_record_id: record.id,
      });
      if (linkedRow === null) {
        return null;
      }
      row = linkedRow.data;
      setMade(submitted.data);
      setRecordId(record.id);
      setDraftRecord(null);
      setConclusion("");
    }
    setEvidenceRound((round) => round + 1);
    setSaved(row);
    return row;
  };

  const run = async (intent: "save" | "submit") => {
    setAttempted(intent);
    setFailure(null);
    const found: Record<string, string> = { ...formatErrors, ...built.errors };
    if (intent === "submit" && evidenceNeeded && evidenceCount === 0) {
      found[EVIDENCE_FIELD] = t("contracts.drawer.event.evidenceError");
    }
    if (conclusion.trim().length > MEMO_MAX_LENGTH) {
      found[CONCLUSION_FIELD] = t("contracts.estimates.error.tooLong", {
        max: countText(MEMO_MAX_LENGTH),
      });
    } else if (intent === "submit" && conclusionOwed) {
      found[CONCLUSION_FIELD] = t("contracts.estimates.judgement.required");
    }
    const wrong = [...shownFields, CONCLUSION_FIELD, EVIDENCE_FIELD].filter(
      (name) => name in found,
    );
    if (wrong.length > 0 || built.body === null) {
      // DS-CMP-21: several wrong fields are named by the summary, which takes the focus; one takes it itself.
      setFocusTick((tick) => tick + 1);
      const [only] = wrong;
      if (wrong.length === 1 && only !== undefined) {
        document.getElementById(fieldId(only))?.focus();
      }
      return;
    }
    setBusy(intent);
    try {
      const row = await persist();
      if (row === null) {
        return;
      }
      if (intent === "save") {
        toast.show({
          tone: "positive",
          message: t("contracts.estimates.version.saved", {
            version: formatNumber(row.version_no, { kind: "count" }),
          }),
        });
        return;
      }
      const submitted = await step<EstimateVersion>(
        "POST",
        `${estimateVersionPath(row.id)}/submit`,
        { comment: null },
      );
      if (submitted === null) {
        return;
      }
      await refresh();
      onSubmitted(submitted.data);
    } catch (error) {
      // A refused upload answers its problem; anything else did not reach the server.
      setFailure(error instanceof ApiProblem ? error : "unreached");
    } finally {
      setBusy(null);
      void refresh();
    }
  };

  const dirty = form !== clean || files.length > 0 || conclusion !== "";
  const stale = saved !== null && form !== clean;
  const locked = methodLocked(estimate);
  const title =
    mode.kind === "edit"
      ? t("contracts.estimates.version.title.edit", {
          version: formatNumber(mode.version.version_no, { kind: "count" }),
          code: estimate.element_code,
        })
      : t("contracts.estimates.version.title.new", { code: estimate.element_code });

  const scenarioColumns: readonly LineColumn<ScenarioRow>[] = [
    {
      id: "outcome",
      header: t("contracts.estimates.scenarios.outcome"),
      kind: "text",
      value: (row) => row.outcome,
      width: "w-64 min-w-64",
    },
    {
      id: "amount",
      header: t("contracts.estimates.scenarios.amountIn", { currency }),
      label: t("contracts.estimates.scenarios.amount"),
      kind: "money",
      value: (row) => row.amount,
      currency,
      width: "w-40 min-w-40",
    },
    ...(method === "EXPECTED_VALUE"
      ? [
          {
            id: "probability",
            header: t("contracts.estimates.scenarios.probability"),
            kind: "decimal",
            value: (row: ScenarioRow) => row.probability,
            width: "w-36 min-w-36",
          } satisfies LineColumn<ScenarioRow>,
        ]
      : []),
  ];
  const setScenario = (rowId: string, column: string, value: string) => {
    if (!(SCENARIO_COLUMNS as readonly string[]).includes(column)) {
      return;
    }
    const name = column as ScenarioColumn;
    change({
      ...form,
      scenarios: form.scenarios.map((row) => (row.id === rowId ? { ...row, [name]: value } : row)),
    });
  };

  const memberField = (member: Member) => {
    if (member.type === "flag") {
      return (
        <label key={member.id} className="flex items-center gap-2 text-body text-fg-1">
          <input
            type="checkbox"
            id={fieldId(member.id)}
            checked={form.flags[member.id] === true}
            onChange={(event) => setFlag(member.id, event.target.checked)}
          />
          {t(member.label)}
        </label>
      );
    }
    const label = t(member.label);
    const typed = form.values[member.id] ?? "";
    const optional = !member.required;
    const error = shown(member.id);
    if (member.type === "money") {
      const conservative = form.values.most_conservative_amount ?? "";
      const unconstrained = form.values.unconstrained_amount ?? "";
      const hint =
        variable &&
        member.id === "constrained_amount" &&
        conservative.trim() !== "" &&
        unconstrained.trim() !== ""
          ? t("contracts.estimates.constrainedHint", {
              low: conservative.trim(),
              high: unconstrained.trim(),
            })
          : undefined;
      return (
        <Field
          key={member.id}
          name={member.id}
          label={`${label} (${currency})`}
          optional={optional}
          required={member.required}
          help={hint}
          error={error}
          width="money"
        >
          {(control) => (
            <MoneyInput
              control={control}
              currency={currency}
              value={typed}
              onChange={(value) => setValue(member.id, value)}
              onFormatError={(message) => setFormatError(member.id, message)}
              invalid={error !== null}
            />
          )}
        </Field>
      );
    }
    if (member.type === "date") {
      return (
        <Field
          key={member.id}
          name={member.id}
          label={label}
          optional={optional}
          required={member.required}
          error={error}
          width="date"
        >
          {(control) => (
            <DateInput
              control={control}
              value={typed}
              onChange={(value) => setValue(member.id, value)}
              onFormatError={(message) => setFormatError(member.id, message)}
              invalid={error !== null}
            />
          )}
        </Field>
      );
    }
    return (
      <TextField
        key={member.id}
        name={member.id}
        label={member.type === "rate" ? t("contracts.estimates.field.percentOf", { label }) : label}
        value={typed}
        onChange={(value) => setValue(member.id, value)}
        optional={optional}
        required={member.required}
        error={error}
        width="money"
        inputMode={member.type === "integer" ? "numeric" : "decimal"}
      />
    );
  };

  const answered: unknown =
    job !== undefined && (job.state === "SUCCEEDED" || job.state === "SUCCEEDED_WITH_EXCEPTIONS")
      ? job.result?.summary
      : null;
  const previewSummary = isImpact(answered) ? answered : null;
  // A summary the API does not answer to this reader: the notice stands where the table would, and
  // "Run preview", which would be answered the same, is not offered (SCREENS §8.4 rev 1.79).
  const previewWithheld = previewSummary === null && summaryWithheld(job);
  const previewFailure: Failure | null = previewUnreached ? "unreached" : preview.problem;
  const previewLabel = t("contracts.drawer.preview.running");
  const runAgain =
    versionId === null ? null : (
      <div>
        <Button
          variant="secondary"
          size="sm"
          disabledReason={
            preview.pending || job?.state === "QUEUED" || job?.state === "RUNNING"
              ? t("contracts.drawer.preview.running")
              : undefined
          }
          onClick={() => void runPreview()}
        >
          {t("contracts.estimates.preview.run")}
        </Button>
      </div>
    );

  return (
    <Drawer
      open
      wide
      title={title}
      initialFocus="field"
      dirty={dirty}
      submitting={busy !== null}
      banner={<FailureNotice failure={failure} fields={shownFields} placedRules={placedRules} />}
      secondaryAction={{
        label: t("contracts.estimates.version.saveDraft"),
        onAction: () => void run("save"),
      }}
      primaryAction={{
        label: t("contracts.drawer.submitForApproval"),
        onAction: () => void run("submit"),
        // A member who may not record the conclusion stores the draft; a holder of the permission
        // completes it (SCREENS §8.4 as bound, rev 1.64).
        disabledReason: errorCorrection
          ? t("contracts.estimates.errorCorrection.blocked")
          : asksConclusion && !canJudge
            ? t("contracts.estimates.judgement.needsPermission")
            : undefined,
      }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-03-drawer-estimate-version"
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void run("save");
        }}
      >
        <ErrorSummary errors={entries} submitCount={focusTick} />
        <dl className="flex flex-wrap gap-x-8 gap-y-3">
          {variable && estimate.vc_element_type !== null ? (
            <ReadOnlyItem label={t("contracts.estimates.element.vcType")}>
              {elementTypeLabel(estimate.vc_element_type)}
            </ReadOnlyItem>
          ) : null}
          <ReadOnlyItem label={t("contracts.estimates.element.method")}>
            <MethodChip method={method} locked={locked} />
          </ReadOnlyItem>
        </dl>
        <Field
          name="effective_date"
          label={t("contracts.estimates.field.effectiveDate")}
          required
          error={shown("effective_date")}
          width="date"
        >
          {(control) => (
            <DateInput
              control={control}
              value={form.effectiveDate}
              onChange={(value) => change({ ...form, effectiveDate: value })}
              onFormatError={(message) => setFormatError("effective_date", message)}
              invalid={shown("effective_date") !== null}
            />
          )}
        </Field>
        {variable ? (
          <LineEditor<ScenarioRow>
            title={t("contracts.estimates.scenarios.title")}
            countLabel={(count, formatted) =>
              t("contracts.estimates.scenarios.count", { count, formatted })
            }
            columns={scenarioColumns}
            rows={form.scenarios}
            rowId={(row) => row.id}
            name="scenarios"
            cellName={(rowId, column) => scenarioField(form.scenarios, rowId, column)}
            errors={errors}
            onChange={setScenario}
            onFormatError={setFormatError}
            addLabel={t("contracts.estimates.scenarios.add")}
            onAdd={() =>
              change({ ...form, scenarios: [...form.scenarios, emptyScenario(nextScenarioId())] })
            }
            removeLabel={(_, index) =>
              t("contracts.estimates.scenarios.remove", {
                position: formatNumber(index + 1, { kind: "count" }),
              })
            }
            onRemove={(rowId) =>
              change({ ...form, scenarios: form.scenarios.filter((row) => row.id !== rowId) })
            }
            emptyText={t("contracts.estimates.scenarios.empty")}
            testId="SF-03-grid-estimate-scenarios"
          />
        ) : null}
        <div className="flex flex-wrap items-start gap-4">{members.map(memberField)}</div>
        {variable ? (
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 text-body-sm font-medium text-fg-1">
              {t("contracts.estimates.factors.legend")}
            </legend>
            {CONSTRAINT_FACTORS.map((factor) => (
              <label key={factor} className="flex items-center gap-2 text-body text-fg-1">
                <input
                  type="checkbox"
                  checked={form.flags[factorFlag(factor)] === true}
                  onChange={(event) => setFlag(factorFlag(factor), event.target.checked)}
                />
                {t(`contracts.estimates.factors.${factor}`)}
              </label>
            ))}
          </fieldset>
        ) : null}
        {kind === "EAC" ? (
          <div className="flex flex-col gap-2">
            <RadioGroup<EacClassification>
              legend={t("contracts.estimates.classification.legend")}
              options={[
                {
                  value: "CHANGE_IN_ESTIMATE",
                  label: t("contracts.estimates.classification.CHANGE_IN_ESTIMATE"),
                },
                {
                  value: "ERROR_CORRECTION",
                  label: t("contracts.estimates.classification.ERROR_CORRECTION"),
                },
              ]}
              value={form.classification}
              onChange={(value) => setForm({ ...form, classification: value })}
            />
            {errorCorrection ? (
              <Banner
                tone="info"
                announce="live"
                headingLevel={3}
                title={t("contracts.estimates.errorCorrection.info")}
              />
            ) : null}
          </div>
        ) : null}
        <TextField
          name="rationale"
          label={t("contracts.drawer.rationale")}
          value={form.rationale}
          onChange={(value) => change({ ...form, rationale: value })}
          required
          error={shown("rationale")}
          width="full"
          multiline
        />
        {variable && recordId !== null ? (
          <dl>
            <ReadOnlyItem label={t("contracts.estimates.judgement.label")}>
              {record === null
                ? t("contracts.estimates.judgement.linked")
                : replaced
                  ? `${record.judgement_no} · ${record.conclusion} (${judgementStatusLabel(record.status)})`
                  : `${record.judgement_no} · ${record.conclusion}`}
            </ReadOnlyItem>
          </dl>
        ) : null}
        {conclusionShown ? (
          <TextField
            name={CONCLUSION_FIELD}
            label={t("contracts.estimates.judgement.conclusion")}
            value={conclusion}
            onChange={(value) => {
              setConclusion(value);
              if (failure !== null) {
                setFailure(null);
              }
            }}
            required
            help={t("contracts.estimates.judgement.help")}
            error={shown(CONCLUSION_FIELD)}
            width="full"
            multiline
          />
        ) : null}
        <div className="flex flex-col gap-1">
          <EvidenceField
            key={evidenceRound}
            name={EVIDENCE_FIELD}
            label={t("contracts.drawer.evidence")}
            required={evidenceNeeded}
            files={files}
            onChange={setFiles}
            error={shown(EVIDENCE_FIELD)}
          />
          {(attachments.data ?? []).length === 0 ? null : (
            <div className="flex flex-col gap-0.5">
              <p id={attachedId} className="text-caption text-fg-3">
                {t("contracts.estimates.evidence.attached")}
              </p>
              <ul
                aria-labelledby={attachedId}
                className="flex flex-col gap-0.5 text-body-sm text-fg-1"
              >
                {(attachments.data ?? []).map((item) => (
                  <li key={item.id}>{item.original_filename ?? item.id}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <section
          aria-labelledby={previewId}
          data-testid="SF-03-pane-estimate-preview"
          className="flex flex-col gap-3 border-t border-hairline pt-3"
        >
          <h3 id={previewId} className="text-title-sm text-fg-1">
            {t("contracts.drawer.preview.title")}
          </h3>
          <FailureNotice failure={previewFailure} onRetry={() => void runPreview()} />
          {stale ? (
            <p className="text-body-sm text-fg-2">{t("contracts.estimates.preview.stale")}</p>
          ) : null}
          {previewSummary !== null ? (
            <>
              <EstimatePreview
                summary={previewSummary}
                currency={currency}
                contextPeriod={contextPeriod}
                periodLabel={periodLabel}
              />
              {runAgain}
            </>
          ) : previewWithheld ? (
            <PreviewNotShown />
          ) : job !== undefined && job.state === "FAILED" ? (
            <Banner
              tone="negative"
              title={t("contracts.estimates.preview.failed")}
              announce="live"
              headingLevel={4}
              actions={
                <Button variant="link" onClick={() => void runPreview()}>
                  {t("contracts.estimates.preview.run")}
                </Button>
              }
            >
              {(job.problem?.errors ?? []).length === 0 ? (
                job.problem === null ? null : (
                  <p>{job.problem.title}</p>
                )
              ) : (
                (job.problem?.errors ?? []).map((error) => (
                  <p key={error.message}>{error.message}</p>
                ))
              )}
              <p>{t("common.job.reference", { reference: job.id.slice(0, 8) })}</p>
            </Banner>
          ) : job !== undefined && (job.state === "QUEUED" || job.state === "RUNNING") ? (
            <JobProgress
              label={previewLabel}
              job={job}
              unit={t("contracts.estimates.preview.unit")}
            />
          ) : preview.pending ? (
            <p role="status" className="text-body-sm text-fg-2">
              {previewLabel}
            </p>
          ) : (
            <>
              <p className="text-body-sm text-fg-2">
                {versionId === null
                  ? t("contracts.estimates.preview.waiting")
                  : t("contracts.estimates.preview.notRun")}
              </p>
              {runAgain}
            </>
          )}
        </section>
      </form>
    </Drawer>
  );
}
