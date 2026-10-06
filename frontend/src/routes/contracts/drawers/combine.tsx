// Combine with another contract and Dismiss suggestion (SCREENS §4.9.7; 04 ACT-04, API-R-28 §16.14;
// REQ-CON-009). Combine: contracts of the same customer (`GET /contracts?customer=`), the ASC 606-10-25-9
// criterion and a rationale; `POST /combination-groups`, then `POST /combination-groups/{id}/submit`.
// The drawer gives up a proposal it made and did not submit (SCREENS §4.9.7 rev 1.78; 04 T-CON-19 "The
// `COMBINATION` topic" rev 1.289, `POST /combination-groups/{id}/discard`): before it proposes another
// form, and when it closes. A proposed group is listed on no screen, so one left behind had no exit.
// Dismiss: a rationale of at least 10 characters; `POST /combination-suggestions/{id}/dismiss`.
import { useQuery } from "@tanstack/react-query";
import { useId, useMemo, useState } from "react";

import { RefusalBanner } from "../../../components/feedback/RefusalBanner";
import { useNoAnswer, useToast } from "../../../components/feedback/Toast";
import { Field } from "../../../components/form/Field";
import { MultiSelect } from "../../../components/form/MultiSelect";
import { ReasonField, reasonError } from "../../../components/form/ReasonField";
import { Drawer } from "../../../components/ui/Drawer";
import { Modal } from "../../../components/ui/Modal";
import { useCommand, useCommandKeys } from "../../../lib/api/commands";
import type { ApiProblem } from "../../../lib/api/problems";
import {
  COMBINATION_GROUPS_PATH,
  COMBINATION_SUGGESTIONS_PATH,
  type CombinationSuggestion,
  type Contract,
  CONTRACT_RECORD_KEYS,
  contractsKey,
  EMPTY_CONTRACT_QUERY,
  fetchContractsPage,
  sendCommand,
  sendStep,
} from "../../../lib/api/queries/contracts";
import { placeProblem } from "../../../lib/api/refusals";
import { t } from "../../../lib/i18n/t";
import { type Choice, RadioGroup, requestNumber, useRefreshRecord } from "./common";

type Criterion = "606-10-25-9(a)" | "606-10-25-9(b)" | "606-10-25-9(c)";

// docs/dev-guide.md DG-FE-06: the fields of each form and the members of the body each sends. The
// submission of the group sends no field of the drawer, so what it is refused for is the banner's.
const COMBINE_MEMBERS = {
  contracts: ["contract_ids"],
  criterion: ["criterion"],
  rationale: ["rationale"],
} as const;
const DISMISS_MEMBERS = { rationale: ["rationale"] } as const;

interface GroupDetail {
  readonly id: string;
  readonly approval_request_id: string | null;
}

/** The proposal the drawer made and has not submitted: its group, and the form it was made from. */
interface Proposal {
  readonly groupId: string;
  /** The body of the first step as sent; with the method and the path it names that step. */
  readonly form: string;
}

export interface CombineDrawerProps {
  readonly contract: Contract;
  readonly onClose: () => void;
}

export function CombineDrawer({ contract, onClose }: CombineDrawerProps) {
  const formId = useId();
  const toast = useToast();
  const noAnswer = useNoAnswer();
  // One press creates the group and submits it: the keys of both steps (DG-FE-05 rev 1.156).
  const keys = useCommandKeys();
  const refresh = useRefreshRecord();
  const [selected, setSelected] = useState<readonly string[]>([]);
  const [criterion, setCriterion] = useState<Criterion | null>(null);
  const [rationale, setRationale] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  // The group this drawer created and has not submitted; null before the first step is answered
  // and once the proposal is given up. An accepted submission closes the drawer.
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const placed = useMemo(() => placeProblem(problem, COMBINE_MEMBERS), [problem]);
  const query = { ...EMPTY_CONTRACT_QUERY, customer: contract.customer.id };
  const candidates = useQuery({
    queryKey: contractsKey(query),
    queryFn: () => fetchContractsPage(query, null, null),
  });
  const options: readonly Choice<string>[] = (candidates.data?.items ?? [])
    .filter((item) => item.id !== contract.id)
    .map((item) => ({ value: item.id, label: item.external_id }));
  const criteria: readonly Choice<Criterion>[] = [
    { value: "606-10-25-9(a)", label: t("contracts.drawer.combine.criterion.a") },
    { value: "606-10-25-9(b)", label: t("contracts.drawer.combine.criterion.b") },
    { value: "606-10-25-9(c)", label: t("contracts.drawer.combine.criterion.c") },
  ];

  /**
   * Gives up the proposal the drawer made: `POST /combination-groups/{id}/discard`, without a body,
   * under a key of its own. Answers the refusal, or null. Whatever the API answers, the drawer has
   * no proposal afterwards and forgets its keys: the kept key of the first step would replay the
   * stored answer of that group — which names it `PROPOSED` whatever became of it (measured) — and
   * the submission behind it would be refused. No answer rejects, and both stay.
   */
  const giveUp = async (made: Proposal): Promise<ApiProblem | null> => {
    const discarded = await sendCommand<GroupDetail>(
      keys,
      "POST",
      `${COMBINATION_GROUPS_PATH}/${made.groupId}/discard`,
      undefined,
    );
    keys.clear();
    setProposal(null);
    return discarded.ok ? null : discarded.problem;
  };

  const submit = async () => {
    setAttempted(true);
    if (selected.length === 0 || criterion === null || reasonError(rationale) !== null) {
      return;
    }
    const body = {
      contract_ids: [contract.id, ...selected],
      criterion,
      rationale: rationale.trim(),
    };
    const form = JSON.stringify(body);
    setSubmitting(true);
    setProblem(null);
    try {
      // A press with a changed form proposes another combination: the proposal made before is given
      // up first, so that the drawer leaves one proposal at most. An unchanged press continues at
      // the submission, the first step under the key it had.
      if (proposal !== null && proposal.form !== form) {
        const refused = await giveUp(proposal);
        if (refused !== null) {
          setProblem(refused);
          return;
        }
      }
      const created = await sendStep<GroupDetail>(keys, "POST", COMBINATION_GROUPS_PATH, body);
      if (!created.ok) {
        setProblem(created.problem);
        return;
      }
      setProposal({ groupId: created.data.id, form });
      const submitted = await sendCommand<GroupDetail>(
        keys,
        "POST",
        `${COMBINATION_GROUPS_PATH}/${created.data.id}/submit`,
        {},
      );
      if (!submitted.ok) {
        setProblem(submitted.problem);
        return;
      }
      // Submitted: the group waits for approval. The drawer closes below by the caller's `onClose`,
      // not by `close`, which gives a proposal up.
      keys.clear();
      await refresh();
      const requestId = submitted.data.approval_request_id;
      toast.show({
        tone: "positive",
        message:
          requestId === null
            ? t("contracts.drawer.combine.submitted")
            : t("contracts.drawer.submittedForApproval", {
                request: await requestNumber(requestId),
              }),
      });
      onClose();
    } catch {
      // No answer: the drawer keeps its input, and the next press sends the same keys.
      noAnswer();
    } finally {
      setSubmitting(false);
    }
  };

  // Closing gives up a proposal that was not submitted, without a question of its own, and says so
  // (SCREENS §4.9.7 rev 1.78). A refused discard is shown as it comes and the drawer stays: the
  // group is no proposal of the drawer any more, and the next close closes.
  const close = async () => {
    if (proposal === null) {
      onClose();
      return;
    }
    setSubmitting(true);
    setProblem(null);
    try {
      const refused = await giveUp(proposal);
      if (refused !== null) {
        setProblem(refused);
        return;
      }
      toast.show({ tone: "neutral", message: t("contracts.drawer.combine.notSubmitted") });
      onClose();
    } catch {
      // No answer: the drawer stays, and the next close sends the discard under the same key.
      noAnswer();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Drawer
      open
      title={t("contracts.drawer.combine.title")}
      subtitle={contract.external_id}
      initialFocus="field"
      dirty={selected.length > 0 || rationale !== ""}
      submitting={submitting}
      banner={<RefusalBanner problem={problem} placed={placed} />}
      primaryAction={{ label: t("contracts.drawer.submitForApproval"), form: formId }}
      onClose={() => void close()}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-03-drawer-combine"
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <Field
          name="combine-contracts"
          label={t("contracts.drawer.combine.contracts")}
          help={t("contracts.drawer.combine.contractsHelp")}
          error={
            attempted && selected.length === 0
              ? t("contracts.drawer.choose")
              : placed.fields.contracts
          }
          width="text"
        >
          {(control) => (
            <MultiSelect
              control={control}
              options={options}
              values={selected}
              onChange={setSelected}
              invalid={attempted && selected.length === 0}
            />
          )}
        </Field>
        <RadioGroup
          legend={t("contracts.drawer.combine.criterion.label")}
          options={criteria}
          value={criterion}
          onChange={setCriterion}
          error={
            attempted && criterion === null ? t("contracts.drawer.choose") : placed.fields.criterion
          }
        />
        <ReasonField
          name="combine-rationale"
          label={t("contracts.drawer.rationale")}
          value={rationale}
          onChange={setRationale}
          showError={attempted}
          error={placed.fields.rationale}
        />
      </form>
    </Drawer>
  );
}

export interface DismissSuggestionModalProps {
  readonly suggestion: CombinationSuggestion;
  readonly onClose: () => void;
}

export function DismissSuggestionModal({ suggestion, onClose }: DismissSuggestionModalProps) {
  const formId = useId();
  const toast = useToast();
  const [rationale, setRationale] = useState("");
  const [attempted, setAttempted] = useState(false);
  const command = useCommand({
    method: "POST",
    path: `${COMBINATION_SUGGESTIONS_PATH}/${suggestion.id}/dismiss`,
    invalidates: CONTRACT_RECORD_KEYS,
  });
  const placed = useMemo(() => placeProblem(command.problem, DISMISS_MEMBERS), [command.problem]);
  const submit = async () => {
    setAttempted(true);
    if (reasonError(rationale) !== null) {
      return;
    }
    const outcome = await command.submit({ rationale: rationale.trim() });
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t("contracts.drawer.dismiss.done") });
      onClose();
    }
  };
  return (
    <Modal
      open
      variant="form"
      title={t("contracts.drawer.dismiss.title")}
      description={t("contracts.drawer.dismiss.description", {
        contracts: suggestion.contract_external_ids.join(", "),
      })}
      submitting={command.pending}
      primaryAction={{ label: t("contracts.drawer.dismiss.action"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        className="flex flex-col gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <RefusalBanner problem={command.problem} placed={placed} />
        <ReasonField
          name="dismiss-rationale"
          label={t("contracts.drawer.rationale")}
          value={rationale}
          onChange={setRationale}
          showError={attempted}
          error={placed.fields.rationale}
        />
      </form>
    </Modal>
  );
}
