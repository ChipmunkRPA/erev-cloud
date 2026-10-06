// SF-05 "Record estimate-versus-error judgement" (SCREENS_B §1.1 rev 1.42, J-14.1; PRD rev 1.59 J-14.1,
// ACT-12; DESIGN_SYSTEM DS-CMP-09 modal drawer, DS-CMP-21; 04 T-CON-19, `POST /judgements` and
// `/submit`; supervisor ruling R-100 (a) and item CLO-JDG-ESTERR-UI-1; BUILD_SPEC CLO-23). The judgement
// whether an amount found after the lock corrects an error or changes an estimate is the Revenue
// Accountant's: on a locked period a holder of `judgement.create` records it here, on its own, and it
// goes to review; the same fields are part of "Request reopen" for a requester who holds the permission.
// The record's subject is the contract — 04 T-CON-19 admits no period as a subject — so nothing ties it
// to the period, and a reopen request names it in its comment.
import { useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";

import { Banner } from "../../components/feedback/Banner";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { useToast } from "../../components/feedback/Toast";
import { Combobox } from "../../components/form/Combobox";
import { Field } from "../../components/form/Field";
import { Drawer } from "../../components/ui/Drawer";
import { type CommandKeys, useCommandKeys } from "../../lib/api/commands";
import { fetchListPage } from "../../lib/api/lists";
import type { ApiProblem } from "../../lib/api/problems";
import {
  CONTRACTS_PATH,
  type ContractListItem,
  sendCommand,
  sendStep,
} from "../../lib/api/queries/contracts";
import { JUDGEMENTS_PATH } from "../../lib/api/queries/periods";
import type { Period } from "../../lib/api/queries/tenant";
import { queryKey } from "../../lib/api/query-keys";
import { t } from "../../lib/i18n/t";
import { TextField } from "../contracts/drawers/common";

const CONTRACT_LIMIT = 200;

async function fetchEntityContracts(entityCode: string): Promise<readonly ContractListItem[]> {
  const page = await fetchListPage<ContractListItem>(CONTRACTS_PATH, { entity: entityCode }, null, {
    limit: CONTRACT_LIMIT,
    count: false,
  });
  return page.items;
}

/** The fields of an estimate-versus-error judgement, as typed. */
export interface JudgementDraft {
  readonly contractId: string | null;
  readonly conclusion: string;
  readonly rationale: string;
}

export const EMPTY_JUDGEMENT: JudgementDraft = { contractId: null, conclusion: "", rationale: "" };

export interface JudgementErrors {
  readonly contract: string | null;
  readonly conclusion: string | null;
  readonly rationale: string | null;
}

export function judgementErrors(draft: JudgementDraft): JudgementErrors {
  return {
    contract: draft.contractId === null ? t("close.reopen.contractError") : null,
    conclusion: draft.conclusion.trim() === "" ? t("close.reopen.conclusionError") : null,
    rationale: draft.rationale.trim() === "" ? t("close.reopen.rationaleError") : null,
  };
}

export type JudgementOutcome =
  | { readonly ok: true; readonly id: string; readonly number: string | null }
  | { readonly ok: false; readonly problem: ApiProblem; readonly createdId: string | null };

/**
 * Creates the `ESTIMATE_VS_ERROR` record of the contract and submits it for review. `createdId` is the
 * record of an earlier attempt whose submission failed: it is submitted again, not created twice.
 * The two commands take their keys from `keys`, the keys of the drawer that sends them (DG-FE-05 rev
 * 1.156): the create keeps its key after it succeeded, so a press repeated after the submission got
 * no answer replays the record the API created instead of creating a second one.
 */
export async function recordJudgement(
  keys: CommandKeys,
  draft: JudgementDraft,
  createdId: string | null = null,
): Promise<JudgementOutcome> {
  let id = createdId;
  let number: string | null = null;
  if (id === null) {
    const created = await sendStep<{
      readonly id: string;
      readonly judgement_no?: string | null;
    }>(keys, "POST", JUDGEMENTS_PATH, {
      topic: "ESTIMATE_VS_ERROR",
      subject_type: "contract",
      subject_id: draft.contractId,
      conclusion: draft.conclusion.trim(),
      rationale: draft.rationale.trim(),
    });
    if (!created.ok) {
      return { ok: false, problem: created.problem, createdId: null };
    }
    id = created.data.id;
    number = created.data.judgement_no ?? null;
  }
  const submitted = await sendCommand<{ readonly judgement_no?: string | null } | null>(
    keys,
    "POST",
    `${JUDGEMENTS_PATH}/${id}/submit`,
    {},
  );
  if (!submitted.ok) {
    return { ok: false, problem: submitted.problem, createdId: id };
  }
  return { ok: true, id, number: submitted.data?.judgement_no ?? number };
}

export interface JudgementFieldsProps {
  readonly entityCode: string;
  /** The prefix of the field names, for example `reopen`. */
  readonly namePrefix: string;
  readonly draft: JudgementDraft;
  readonly onChange: (draft: JudgementDraft) => void;
  /** The errors to show; null before the first attempt to send. */
  readonly errors: JudgementErrors | null;
}

/** "Contract", "Conclusion" and "Rationale" of the judgement; the contracts are the entity's. */
export function JudgementFields({
  entityCode,
  namePrefix,
  draft,
  onChange,
  errors,
}: JudgementFieldsProps) {
  const contracts = useQuery({
    queryKey: queryKey("contracts", "tenant", { entity: entityCode, purpose: "reopen-judgement" }),
    queryFn: () => fetchEntityContracts(entityCode),
  });
  const options = (contracts.data ?? []).map((contract) => ({
    value: contract.id,
    label: `${contract.external_id} · ${contract.customer.name}`,
  }));
  return (
    <>
      <Field
        name={`${namePrefix}-contract`}
        label={t("close.reopen.contract")}
        required
        error={errors?.contract ?? null}
      >
        {(control) => (
          <Combobox<string>
            control={control}
            options={options}
            value={draft.contractId}
            onChange={(contractId) => onChange({ ...draft, contractId })}
            invalid={errors !== null && errors.contract !== null}
          />
        )}
      </Field>
      <TextField
        name={`${namePrefix}-conclusion`}
        label={t("close.reopen.conclusion")}
        required
        multiline
        value={draft.conclusion}
        onChange={(conclusion) => onChange({ ...draft, conclusion })}
        error={errors?.conclusion ?? null}
      />
      <TextField
        name={`${namePrefix}-rationale`}
        label={t("close.reopen.rationale")}
        required
        multiline
        value={draft.rationale}
        onChange={(rationale) => onChange({ ...draft, rationale })}
        error={errors?.rationale ?? null}
      />
    </>
  );
}

export interface JudgementDrawerProps {
  readonly period: Period;
  readonly periodLabel: string;
  readonly bookLabel: string;
  /** Opens SF-08:report `judgement_register` in the period's context; null while it is not built. */
  readonly onOpenRegister: (() => void) | null;
  readonly onClose: () => void;
}

export function JudgementDrawer({
  period,
  periodLabel,
  bookLabel,
  onOpenRegister,
  onClose,
}: JudgementDrawerProps) {
  const toast = useToast();
  const keys = useCommandKeys();
  const formId = useId();
  const [draft, setDraft] = useState<JudgementDraft>(EMPTY_JUDGEMENT);
  const [attempted, setAttempted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [unsent, setUnsent] = useState(false);
  // The record of an attempt whose submission failed, so that it is not created a second time.
  const [createdId, setCreatedId] = useState<string | null>(null);
  const errors = judgementErrors(draft);
  const entityCode = period.entity.code;

  const submit = async () => {
    setAttempted(true);
    if (Object.values(errors).some((value) => value !== null)) {
      return;
    }
    setSubmitting(true);
    setProblem(null);
    setUnsent(false);
    try {
      const outcome = await recordJudgement(keys, draft, createdId);
      if (!outcome.ok) {
        setCreatedId(outcome.createdId);
        setProblem(outcome.problem);
        return;
      }
      toast.show({
        tone: "positive",
        message:
          outcome.number === null
            ? t("close.judgement.doneUnnumbered")
            : t("close.judgement.done", { number: outcome.number }),
        action:
          onOpenRegister === null
            ? undefined
            : { label: t("close.reopen.judgementRegister"), onAction: onOpenRegister },
      });
      onClose();
    } catch {
      setUnsent(true);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Drawer
      open
      title={t("close.judgement.title", { period: periodLabel })}
      subtitle={`${entityCode} · ${bookLabel}`}
      dirty={draft !== EMPTY_JUDGEMENT}
      submitting={submitting}
      initialFocus="field"
      banner={
        problem === null && !unsent ? undefined : (
          <div className="flex flex-col gap-2">
            {unsent ? <Banner tone="negative" title={t("close.judgement.network")} /> : null}
            <RefusalBanner problem={problem} />
          </div>
        )
      }
      primaryAction={{ label: t("close.judgement.submit"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-05-drawer-judgement"
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <Banner tone="info" announce="static" title={t("close.judgement.info")} />
        <JudgementFields
          entityCode={entityCode}
          namePrefix="judgement"
          draft={draft}
          onChange={setDraft}
          errors={attempted ? errors : null}
        />
      </form>
    </Drawer>
  );
}
